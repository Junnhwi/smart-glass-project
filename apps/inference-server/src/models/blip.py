from functools import lru_cache

import torch
from transformers import BlipForConditionalGeneration, BlipProcessor


device = "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache(maxsize=1)
def get_blip_components():
    processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
    model = BlipForConditionalGeneration.from_pretrained(
        "Salesforce/blip-image-captioning-base"
    ).to(device)
    return device, model, processor
