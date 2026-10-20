"""PNG images for multimodal DSPy inputs."""

import dspy


def png_images(b64_pngs: list[str]) -> list[dspy.Image]:
    """Base64-encoded PNGs as DSPy image inputs."""
    return [dspy.Image(f"data:image/png;base64,{b64}") for b64 in b64_pngs]
