import os
import ssl

os.environ["HF_HUB_DISABLE_SSL_VERIFICATION"] = "1"
os.environ["CURL_CA_BUNDLE"] = ""
os.environ["PYTHONHTTPSVERIFY"] = "0"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import httpx
_orig_client_init = httpx.Client.__init__
def _patched_client_init(self, *args, **kwargs):
    kwargs['verify'] = False
    _orig_client_init(self, *args, **kwargs)
httpx.Client.__init__ = _patched_client_init

import torch
from PIL import Image
import numpy as np
from transformers import SiglipImageProcessor, SiglipVisionModel

model_id = "google/siglip-base-patch16-224"
print("Loading SigLIP Vision Model & Image Processor:", model_id)

processor = SiglipImageProcessor.from_pretrained(model_id)
model = SiglipVisionModel.from_pretrained(model_id)

img = Image.fromarray(np.zeros((224, 224, 3), dtype=np.uint8))
inputs = processor(images=img, return_tensors="pt")

with torch.no_grad():
    outputs = model(**inputs)
    # pooler_output es la representación global de la imagen (768 dims)
    image_features = outputs.pooler_output
    image_features = image_features / image_features.norm(p=2, dim=-1, keepdim=True)

print("SigLIP image embedding shape:", image_features.shape)
print("SigLIP image embedding dtype:", image_features.dtype)
print("SUCCESS - Image Embedding Extracted Cleanly!")
