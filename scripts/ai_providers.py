import base64
import mimetypes
import sys
from pathlib import Path

from anthropic import Anthropic
from google import genai
from google.genai import types
from ollama import Client as OllamaClient
from openai import OpenAI


SUPPORTED_PROVIDERS = {
    "openai",
    "gemini",
    "claude",
    "ollama",
}


TEST_CASE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "test_cases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "test_case_id": {
                        "type": "string"
                    },
                    "test_case_title": {
                        "type": "string"
                    },
                    "precondition": {
                        "type": "string"
                    },
                    "test_steps": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        }
                    },
                    "expected_result": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        }
                    },
                    "status": {
                        "type": "string"
                    },
                    "note": {
                        "type": "string"
                    },
                },
                "required": [
                    "test_case_id",
                    "test_case_title",
                    "precondition",
                    "test_steps",
                    "expected_result",
                    "status",
                    "note",
                ],
            },
        }
    },
    "required": [
        "test_cases"
    ],
}


SUPPORTED_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
}


def validate_image_paths(image_paths):
    """
    Validate design/screenshot image paths.
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
                f"Design image is not a file: {path}"
            )

        if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            raise ValueError(
                f"Unsupported image format: {path}"
            )

        validated.append(path)

    return validated


def image_to_data_url(image_path):
    """
    Convert local image into a data URL for OpenAI.
    """

    path = Path(image_path)

    mime_type, _ = mimetypes.guess_type(
        path.name
    )

    if not mime_type:
        raise ValueError(
            f"Could not determine MIME type: {path}"
        )

    encoded = base64.b64encode(
        path.read_bytes()
    ).decode("utf-8")

    return (
        f"data:{mime_type};base64,{encoded}"
    )


def image_to_bytes_part(image_path):
    """
    Convert local image into Gemini image part.
    """

    path = Path(image_path)

    mime_type, _ = mimetypes.guess_type(
        path.name
    )

    if not mime_type:
        raise ValueError(
            f"Could not determine MIME type: {path}"
        )

    return types.Part.from_bytes(
        data=path.read_bytes(),
        mime_type=mime_type,
    )


def generate_with_openai(
    api_key,
    model,
    prompt,
    image_paths=None,
):
    """
    Generate response using OpenAI Responses API.
    """

    client = OpenAI(
        api_key=api_key
    )

    content = [
        {
            "type": "input_text",
            "text": prompt,
        }
    ]

    for image_path in (
        image_paths or []
    ):
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


def generate_with_gemini(
    api_key,
    model,
    prompt,
    image_paths=None,
):
    """
    Generate response using Google Gemini API.
    """

    client = genai.Client(
        api_key=api_key
    )

    contents = []

    for image_path in (
        image_paths or []
    ):
        contents.append(
            image_to_bytes_part(
                image_path
            )
        )

    contents.append(prompt)

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        ),
    )

    if not response.text:
        raise ValueError(
            "Gemini returned no text content."
        )

    return response.text


def generate_with_claude(
    api_key,
    model,
    prompt,
    max_tokens=16000,
    image_paths=None,
):
    """
    Generate response using Anthropic Claude.
    """

    client = Anthropic(
        api_key=api_key
    )

    content = []

    for image_path in (
        image_paths or []
    ):
        path = Path(image_path)

        mime_type, _ = mimetypes.guess_type(
            path.name
        )

        if not mime_type:
            raise ValueError(
                f"Could not determine MIME type: {path}"
            )

        encoded = base64.b64encode(
            path.read_bytes()
        ).decode("utf-8")

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
        if (
            getattr(
                block,
                "type",
                None,
            )
            == "text"
        ):
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


def generate_with_ollama(
    host,
    model,
    vision_model,
    prompt,
    image_paths=None,
    timeout=600,
    num_ctx=32768,
    temperature=0,
):
    """
    Generate response using local Ollama.

    If images are supplied, the vision model is used.
    Otherwise the normal text model is used.
    """

    image_paths = validate_image_paths(
        image_paths
    )

    selected_model = (
        vision_model
        if image_paths
        else model
    )

    if not selected_model:
        raise ValueError(
            "Ollama model is not configured."
        )

    print(
        "[AI] Ollama host: "
        f"{host}"
    )

    print(
        "[AI] Ollama model: "
        f"{selected_model}"
    )

    if image_paths:
        print(
            "[AI] Ollama vision mode: "
            f"{len(image_paths)} image(s)"
        )

    client = OllamaClient(
        host=host,
        timeout=timeout,
    )

    messages = []

    # Ollama supports image paths directly
    # for multimodal models.
    message = {
        "role": "user",
        "content": prompt,
    }

    if image_paths:
        message["images"] = [
            str(path)
            for path in image_paths
        ]

    messages.append(message)

    response = client.chat(
        model=selected_model,
        messages=messages,
        format=TEST_CASE_JSON_SCHEMA,
        options={
            "temperature": temperature,
            "num_ctx": num_ctx,
        },
    )

    content = response.message.content

    if not content:
        raise ValueError(
            "Ollama returned no text content."
        )

    return content


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

    invalid = [
        provider
        for provider in providers
        if provider not in SUPPORTED_PROVIDERS
    ]

    if invalid:
        raise ValueError(
            "Unsupported AI provider(s): "
            + ", ".join(invalid)
            + ". Supported providers: "
            + ", ".join(
                sorted(
                    SUPPORTED_PROVIDERS
                )
            )
        )

    if len(providers) != len(
        set(providers)
    ):
        raise ValueError(
            "AITLC_PROVIDER_ORDER "
            "cannot contain duplicate providers."
        )

    if not providers:
        raise ValueError(
            "AITLC_PROVIDER_ORDER "
            "cannot be empty."
        )

    return providers


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
    ollama_host="http://localhost:11434",
    ollama_model="gemma4",
    ollama_vision_model="gemma4",
    ollama_timeout=600,
    ollama_num_ctx=32768,
    ollama_temperature=0,
    image_paths=None,
):
    """
    Generate AI response according to
    configurable provider order.

    Supported providers:

        openai
        gemini
        claude
        ollama

    Example:

        openai,gemini,claude,ollama

    Means:

        OpenAI
          ↓ fail
        Gemini primary
          ↓ fail
        Gemini fallback
          ↓ fail
        Claude
          ↓ fail
        Ollama
    """

    providers = parse_provider_order(
        provider_order
    )

    errors = []

    print(
        "[AI] Provider order: "
        + " → ".join(providers)
    )

    for provider in providers:

        # ========================================================
        # OPENAI
        # ========================================================

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

        # ========================================================
        # GEMINI
        # ========================================================

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

            # ----------------------------------------------------
            # Gemini primary
            # ----------------------------------------------------

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

            # ----------------------------------------------------
            # Gemini fallback
            # ----------------------------------------------------

            if (
                gemini_fallback_model
                and gemini_fallback_model
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

        # ========================================================
        # CLAUDE
        # ========================================================

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
                    claude_max_tokens,
                    image_paths,
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
        # OLLAMA
        # ========================================================

        if provider == "ollama":

            try:

                print(
                    "[AI] Trying local Ollama..."
                )

                raw = generate_with_ollama(
                    host=ollama_host,
                    model=ollama_model,
                    vision_model=ollama_vision_model,
                    prompt=prompt,
                    image_paths=image_paths,
                    timeout=ollama_timeout,
                    num_ctx=ollama_num_ctx,
                    temperature=ollama_temperature,
                )

                print(
                    "[AI] Ollama generation successful."
                )

                selected_model = (
                    ollama_vision_model
                    if image_paths
                    else ollama_model
                )

                return (
                    raw,
                    f"Ollama/{selected_model}",
                )

            except Exception as exc:

                errors.append(
                    f"Ollama: {exc}"
                )

                print(
                    f"[AI] Ollama failed: {exc}",
                    file=sys.stderr,
                )

                continue

    # ============================================================
    # ALL PROVIDERS FAILED
    # ============================================================

    raise RuntimeError(
        "All configured AI providers failed.\n"
        + "\n".join(errors)
    )