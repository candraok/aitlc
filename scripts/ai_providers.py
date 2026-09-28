import base64
import mimetypes
import sys
from pathlib import Path

from anthropic import Anthropic
from google import genai
from google.genai import types
from openai import OpenAI


SUPPORTED_IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def validate_image_paths(image_paths):
    """
    Validate all referenced image files before sending them to an AI provider.
    """

    if not image_paths:
        return []

    validated = []

    for image_path in image_paths:
        path = Path(image_path).resolve()

        if not path.exists():
            raise FileNotFoundError(
                f"Design image not found: {path}"
            )

        if not path.is_file():
            raise ValueError(
                f"Design reference is not a file: {path}"
            )

        suffix = path.suffix.lower()

        if suffix not in SUPPORTED_IMAGE_TYPES:
            raise ValueError(
                f"Unsupported image type: {path.name}. "
                f"Supported types: "
                f"{', '.join(sorted(SUPPORTED_IMAGE_TYPES.keys()))}"
            )

        validated.append(path)

    return validated


def get_image_mime_type(image_path):
    """
    Return MIME type for an image file.
    """

    path = Path(image_path)

    mime_type = SUPPORTED_IMAGE_TYPES.get(
        path.suffix.lower()
    )

    if mime_type:
        return mime_type

    mime_type, _ = mimetypes.guess_type(
        str(path)
    )

    if not mime_type:
        raise ValueError(
            f"Cannot determine MIME type for image: {path}"
        )

    return mime_type


def read_image_bytes(image_path):
    """
    Read image as bytes.
    """

    with open(image_path, "rb") as file:
        return file.read()


def image_to_data_url(image_path):
    """
    Convert local image into a base64 data URL.
    Used by OpenAI.
    """

    image_bytes = read_image_bytes(image_path)

    encoded = base64.b64encode(
        image_bytes
    ).decode("utf-8")

    mime_type = get_image_mime_type(
        image_path
    )

    return (
        f"data:{mime_type};base64,{encoded}"
    )


# ============================================================
# OPENAI
# ============================================================

def generate_with_openai(
    api_key,
    model,
    prompt,
    image_paths=None,
):
    """
    Generate response using OpenAI Responses API.

    Supports:
    - text-only requests
    - text + multiple images
    """

    client = OpenAI(
        api_key=api_key
    )

    image_paths = validate_image_paths(
        image_paths
    )

    content = [
        {
            "type": "input_text",
            "text": prompt,
        }
    ]

    for image_path in image_paths:

        content.append(
            {
                "type": "input_image",
                "image_url": image_to_data_url(
                    image_path
                ),
                "detail": "high",
            }
        )

    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": content,
            }
        ],
    )

    return response.output_text


# ============================================================
# GEMINI
# ============================================================

def generate_with_gemini(
    api_key,
    model,
    prompt,
    image_paths=None,
):
    """
    Generate response using Gemini.

    Supports:
    - text-only requests
    - text + multiple images
    """

    client = genai.Client(
        api_key=api_key
    )

    image_paths = validate_image_paths(
        image_paths
    )

    contents = []

    for image_path in image_paths:

        image_bytes = read_image_bytes(
            image_path
        )

        mime_type = get_image_mime_type(
            image_path
        )

        contents.append(
            types.Part.from_bytes(
                data=image_bytes,
                mime_type=mime_type,
            )
        )

    contents.append(
        prompt
    )

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        ),
    )

    return response.text


# ============================================================
# CLAUDE
# ============================================================

def generate_with_claude(
    api_key,
    model,
    prompt,
    image_paths=None,
    max_tokens=16000,
):
    """
    Generate response using Anthropic Claude Messages API.

    Supports:
    - text-only requests
    - text + multiple images
    """

    client = Anthropic(
        api_key=api_key
    )

    image_paths = validate_image_paths(
        image_paths
    )

    content = []

    # Images are sent before text.
    # This is recommended for Claude vision requests.
    for image_path in image_paths:

        image_bytes = read_image_bytes(
            image_path
        )

        encoded = base64.b64encode(
            image_bytes
        ).decode("utf-8")

        mime_type = get_image_mime_type(
            image_path
        )

        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": encoded,
                },
            }
        )

    content.append(
        {
            "type": "text",
            "text": prompt,
        }
    )

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {
                "role": "user",
                "content": content,
            }
        ],
    )

    text_blocks = []

    for block in response.content:

        if getattr(
            block,
            "type",
            None,
        ) == "text":

            text_blocks.append(
                block.text
            )

    if not text_blocks:
        raise ValueError(
            "Claude returned no text content."
        )

    return "\n".join(
        text_blocks
    )


# ============================================================
# PROVIDER ORDER
# ============================================================

def parse_provider_order(
    provider_order
):
    """
    Convert:

        openai,gemini,claude

    into:

        ["openai", "gemini", "claude"]
    """

    if not provider_order:

        return [
            "openai",
            "gemini",
            "claude",
        ]

    providers = [
        provider.strip().lower()
        for provider
        in provider_order.split(",")
        if provider.strip()
    ]

    supported = {
        "openai",
        "gemini",
        "claude",
    }

    invalid = [
        provider
        for provider
        in providers
        if provider not in supported
    ]

    if invalid:

        raise ValueError(
            "Unsupported AI provider(s): "
            + ", ".join(invalid)
            + ". Supported providers: "
            + ", ".join(
                sorted(supported)
            )
        )

    if not providers:

        raise ValueError(
            "AITLC_PROVIDER_ORDER cannot be empty."
        )

    duplicates = {
        provider
        for provider in providers
        if providers.count(provider) > 1
    }

    if duplicates:

        raise ValueError(
            "Duplicate provider(s) in "
            "AITLC_PROVIDER_ORDER: "
            + ", ".join(
                sorted(duplicates)
            )
        )

    return providers


# ============================================================
# MAIN AI ROUTER
# ============================================================

def generate_ai_response(
    prompt,
    provider_order,
    openai_api_key,
    openai_model,
    gemini_api_key,
    gemini_model,
    gemini_fallback_model,
    claude_api_key,
    claude_model,
    claude_max_tokens=16000,
    image_paths=None,
):
    """
    Generate AI response according to configurable provider order.

    Example:

        AITLC_PROVIDER_ORDER=openai,gemini,claude

    Flow:

        OpenAI
          ↓ fail
        Gemini primary
          ↓ fail
        Gemini fallback
          ↓ fail
        Claude

    If:

        AITLC_PROVIDER_ORDER=claude,gemini,openai

    Flow:

        Claude
          ↓ fail
        Gemini primary
          ↓ fail
        Gemini fallback
          ↓ fail
        OpenAI
    """

    providers = parse_provider_order(
        provider_order
    )

    image_paths = validate_image_paths(
        image_paths
    )

    errors = []

    print(
        "[AI] Provider order: "
        + " → ".join(providers)
    )

    if image_paths:

        print(
            "[AI] Design images: "
            + str(len(image_paths))
        )

        for image_path in image_paths:

            print(
                f"[AI]   - {image_path}"
            )

    else:

        print(
            "[AI] Design images: none"
        )

    for provider in providers:

        # ====================================================
        # OPENAI
        # ====================================================

        if provider == "openai":

            if not openai_api_key:

                print(
                    "[AI] OpenAI skipped: "
                    "OPENAI_API_KEY is not configured."
                )

                errors.append(
                    "OpenAI: API key not configured."
                )

                continue

            try:

                print(
                    "[AI] Trying OpenAI: "
                    f"{openai_model}"
                )

                raw = generate_with_openai(
                    openai_api_key,
                    openai_model,
                    prompt,
                    image_paths,
                )

                print(
                    "[AI] OpenAI generation successful."
                )

                return (
                    raw,
                    f"OpenAI/{openai_model}",
                )

            except Exception as exc:

                errors.append(
                    f"OpenAI: {exc}"
                )

                print(
                    f"[AI] OpenAI failed: {exc}",
                    file=sys.stderr,
                )

                continue

        # ====================================================
        # GEMINI
        # ====================================================

        if provider == "gemini":

            if not gemini_api_key:

                print(
                    "[AI] Gemini skipped: "
                    "GEMINI_API_KEY is not configured."
                )

                errors.append(
                    "Gemini: API key not configured."
                )

                continue

            # ------------------------------------------------
            # Gemini primary
            # ------------------------------------------------

            try:

                print(
                    "[AI] Trying Gemini: "
                    f"{gemini_model}"
                )

                raw = generate_with_gemini(
                    gemini_api_key,
                    gemini_model,
                    prompt,
                    image_paths,
                )

                print(
                    "[AI] Gemini primary "
                    "generation successful."
                )

                return (
                    raw,
                    f"Gemini/{gemini_model}",
                )

            except Exception as exc:

                errors.append(
                    f"Gemini primary: {exc}"
                )

                print(
                    f"[AI] Gemini primary failed: {exc}",
                    file=sys.stderr,
                )

            # ------------------------------------------------
            # Gemini fallback
            # ------------------------------------------------

            if (
                gemini_fallback_model
                and
                gemini_fallback_model
                != gemini_model
            ):

                try:

                    print(
                        "[AI] Trying Gemini fallback: "
                        f"{gemini_fallback_model}"
                    )

                    raw = generate_with_gemini(
                        gemini_api_key,
                        gemini_fallback_model,
                        prompt,
                        image_paths,
                    )

                    print(
                        "[AI] Gemini fallback "
                        "generation successful."
                    )

                    return (
                        raw,
                        f"Gemini/{gemini_fallback_model}",
                    )

                except Exception as exc:

                    errors.append(
                        f"Gemini fallback: {exc}"
                    )

                    print(
                        f"[AI] Gemini fallback failed: {exc}",
                        file=sys.stderr,
                    )

            continue

        # ====================================================
        # CLAUDE
        # ====================================================

        if provider == "claude":

            if not claude_api_key:

                print(
                    "[AI] Claude skipped: "
                    "CLAUDE_API_KEY is not configured."
                )

                errors.append(
                    "Claude: API key not configured."
                )

                continue

            try:

                print(
                    "[AI] Trying Claude: "
                    f"{claude_model}"
                )

                raw = generate_with_claude(
                    claude_api_key,
                    claude_model,
                    prompt,
                    image_paths,
                    claude_max_tokens,
                )

                print(
                    "[AI] Claude generation successful."
                )

                return (
                    raw,
                    f"Claude/{claude_model}",
                )

            except Exception as exc:

                errors.append(
                    f"Claude: {exc}"
                )

                print(
                    f"[AI] Claude failed: {exc}",
                    file=sys.stderr,
                )

                continue

    # ========================================================
    # ALL PROVIDERS FAILED
    # ========================================================

    raise RuntimeError(
        "All configured AI providers failed.\n"
        + "\n".join(errors)
    )