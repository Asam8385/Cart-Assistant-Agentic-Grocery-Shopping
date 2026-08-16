from __future__ import annotations

from agent_framework import(
   Agent,
   Content,
   Message
)

from agent_framework.foundry import (
   FoundryChatClient
)


from ._structured import (
   parse_structured_response,
)

from .prompts import (
   IMAGE_ANALYZER_PROMPT
)


from .schemas import (
   ImageAnalysisResult,
)


ALLOWED_IMAGE_MEDIA_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
}


class ImageAnalyzerAgent:
   def __init__(
         self,
         client: FoundryChatClient ,
         * , 
         maximum_image_bytes: int = 10 * 1024 * 1024,
   ) -> None:
        if maximum_image_bytes < 1:
            raise ValueError(
                "maximum_image_bytes must be positive."
            )

        self._maximum_image_bytes = (
            maximum_image_bytes
        )

        self._agent = Agent(
            client=client,
            name="image-analyzer-agent",
            description=(
                "Extracts active, crossed-out and uncertain "
                "items from handwritten shopping lists."
            ),
            instructions=IMAGE_ANALYZER_PROMPT,
            default_options={
                "max_tokens" : 1200,
                
            }
        )

   async def analyze(
            self,
            image_bytes: bytes,
            *,
            media_type: str,
            user_note: str | None = None,
        ) -> ImageAnalysisResult:
        if not image_bytes:
            raise ValueError(
                "The image cannot be empty."
            )

        if len(image_bytes) > self._maximum_image_bytes:
            raise ValueError(
                "The image exceeds the configured size limit."
            )

        normalized_media_type = (
            media_type.strip().lower()
        )

        if (
            normalized_media_type
            not in ALLOWED_IMAGE_MEDIA_TYPES
        ):
            raise ValueError(
                "Unsupported image media type. "
                "Use JPEG, PNG, WEBP or HEIC."
            )
            
        note = (
            user_note.strip()
            if user_note
            else ""
        )

        if note:
            instruction += (
                "\nThe user's accompanying preference text is "
                "provided only for context:\n"
                f"{note[:2000]}"
            )

        message = Message(
            "user" , 
            [
                instruction , 
                Content.from_data(
                    image_bytes,
                    normalized_media_type,
                ),

            ],
        )

        response = await self._agent.run(
            message,
            options={
                "response_format": ImageAnalysisResult,
                "max_tokens":1200,
            }
        )


        return parse_structured_response(
            response,
            ImageAnalysisResult,
        )
            
    
