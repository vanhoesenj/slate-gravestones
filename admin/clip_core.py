"""CLIP image embeddings for the visual-similarity constellation.
Requires the same install as relief maps: pip3 install torch transformers."""

_model = None


def get_model():
    global _model
    if _model is None:
        from transformers import CLIPModel, CLIPProcessor
        name = "openai/clip-vit-base-patch32"
        _model = (CLIPModel.from_pretrained(name),
                  CLIPProcessor.from_pretrained(name))
    return _model


def embed(img_path):
    import torch
    from PIL import Image
    model, proc = get_model()
    with torch.no_grad():
        inputs = proc(images=Image.open(img_path).convert("RGB"),
                      return_tensors="pt")
        v = model.get_image_features(**inputs)[0]
        v = v / v.norm()
    return [round(float(x), 5) for x in v]
