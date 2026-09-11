from huggingface_hub import HfApi
api = HfApi()
info = api.model_info("Xenova/clip-vit-base-patch32")
for f in info.siblings:
    if "onnx" in f.rfilename:
        print(f.rfilename)
