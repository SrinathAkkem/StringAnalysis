from copy import deepcopy
from typing import List
import torch
from PIL import Image

from surya.schema import OrderBox, OrderResult
from surya.settings import settings
from tqdm import tqdm
import numpy as np


def get_batch_size():
    batch_size = settings.ORDER_BATCH_SIZE
    if batch_size is None:
        batch_size = 4
        if settings.TORCH_DEVICE_MODEL == "mps":
            batch_size = 4
        if settings.TORCH_DEVICE_MODEL == "cuda":
            batch_size = 32
    return batch_size


def rank_elements(arr):
    enumerated_and_sorted = sorted(enumerate(arr), key=lambda x: x[1])
    rank = [0] * len(arr)

    for rank_value, (original_index, value) in enumerate(enumerated_and_sorted):
        rank[original_index] = rank_value

    return rank


def batch_ordering(images: List, bboxes: List[List[List[float]]], model, processor) -> List[OrderResult]:
    assert all([isinstance(image, Image.Image) for image in images])
    assert len(images) == len(bboxes)
    batch_size = get_batch_size()

    images = [image.convert("RGB") for image in images]

    output_order = []
    for i in tqdm(range(0, len(images), batch_size), desc="Finding reading order"):
        batch_bboxes = deepcopy(bboxes[i:i+batch_size])
        batch_images = images[i:i+batch_size]
        orig_sizes = [image.size for image in batch_images]
        model_inputs = processor(images=batch_images, boxes=batch_bboxes)

        batch_pixel_values = model_inputs["pixel_values"]
        batch_bboxes = model_inputs["input_boxes"]
        batch_bbox_mask = model_inputs["input_boxes_mask"]

        batch_bboxes = torch.from_numpy(np.array(batch_bboxes, dtype=np.int32)).to(model.device)
        batch_bbox_mask = torch.from_numpy(np.array(batch_bbox_mask, dtype=np.int32)).to(model.device)
        batch_pixel_values = torch.tensor(np.array(batch_pixel_values), dtype=model.dtype).to(model.device)

        with torch.inference_mode():
            return_dict = model(
                pixel_values=batch_pixel_values,
                decoder_input_boxes=batch_bboxes,
                decoder_input_boxes_mask=batch_bbox_mask
            )
            logits = return_dict["logits"].detach().cpu()

        assert logits.shape[0] == len(batch_images) == len(batch_bboxes)
        for j in range(logits.shape[0]):
            row_logits = logits[j].tolist()
            row_bboxes = bboxes[i+j]
            orig_size = orig_sizes[j]
            ranks = rank_elements(row_logits)

            order_boxes = []
            for row_bbox, rank in zip(row_bboxes, ranks):
                order_box = OrderBox(
                    bbox=row_bbox,
                    position=rank,
                )
                order_boxes.append(order_box)

            result = OrderResult(
                bboxes=order_boxes,
                image_bbox=[0, 0, orig_size[0], orig_size[1]],
            )
            output_order.append(result)
    return output_order






