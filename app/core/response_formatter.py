import re


class ResponseFormatter:

    @staticmethod
    def clean(text: str) -> str:

        if not text:
            return ""

        # remove markdown bold
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)

        # remove markdown headers
        text = re.sub(r"#{1,6}\s*", "", text)

        # normalize spacing
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()