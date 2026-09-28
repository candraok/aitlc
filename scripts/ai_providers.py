import sys

from anthropic import Anthropic
from google import genai
from google.genai import types
from openai import OpenAI


def generate_with_openai(api_key, model, prompt):
    """
    Generate response using OpenAI Responses API.
    """

    client = OpenAI(api_key=api_key)

    response = client.responses.create(
        model=model,
        input=prompt,
    )

    return response.output_text


def generate_with_gemini(api_key, model, prompt):
    """
    Generate response using Gemini API.
    """

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        ),
    )

    return response.text


def generate_with_claude(
    api_key,
    model,
    prompt,
    max_tokens=16000,
):
    """
    Generate response using Anthropic Claude.
    """

    client = Anthropic(
        api_key=api_key
    )

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {
                "role": "user",
                "content": prompt,
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
        for provider in providers
        if provider not in supported
    ]

    if invalid:

        raise ValueError(
            "Unsupported AI provider(s): "
            + ", ".join(invalid)
            + ". Supported providers: "
            + ", ".join(sorted(supported))
        )

    if not providers:

        raise ValueError(
            "AITLC_PROVIDER_ORDER cannot be empty."
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
):
    """
    Generate AI response according to
    configurable provider order.

    Example:

        openai,gemini,claude

    means:

        OpenAI
          ↓ fail
        Gemini primary
          ↓ fail
        Gemini fallback
          ↓ fail
        Claude
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
            # Gemini fallback model
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

    # ============================================================
    # ALL PROVIDERS FAILED
    # ============================================================

    raise RuntimeError(
        "All configured AI providers failed.\n"
        + "\n".join(errors)
    )