import re


class ResponseFormatter:

    @staticmethod
    def clean(text: str) -> str:
        """
        LLM response ko clean readable format mein convert karo.
        Markdown symbols hata do — plain structured text do.
        """
        if not text:
            return ""

        # ## Headers → UPPERCASE line
        text = re.sub(r"#{1,6}\s*(.+)", lambda m: m.group(1).upper(), text)

        # **bold** → plain text
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)

        # *italic* → plain text
        text = re.sub(r"\*(.*?)\*", r"\1", text)

        # `code` → plain (rakhna chahte ho toh comment karo)
        # text = re.sub(r"`(.*?)`", r"\1", text)

        # * bullet ya - bullet → • bullet
        text = re.sub(r"^[\*\-]\s+", "• ", text, flags=re.MULTILINE)

        # Numbered lists theek rakho — 1. 2. 3.
        text = re.sub(r"^\d+\.\s+", lambda m: m.group(0), text,
                      flags=re.MULTILINE)

        # 3+ newlines → 2 newlines
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    @staticmethod
    def to_structured(text: str) -> dict:
        """
        LLM response ko sections mein parse karo.
        Frontend structured response render kar sake.
        """
        sections = []
        current_title = "Response"
        current_lines = []

        for line in text.split("\n"):
            # Header detect karo
            header_match = re.match(r"#{1,6}\s*(.+)", line)
            if header_match:
                if current_lines:
                    sections.append({
                        "title":   current_title,
                        "content": "\n".join(current_lines).strip()
                    })
                current_title = header_match.group(1).strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines:
            sections.append({
                "title":   current_title,
                "content": "\n".join(current_lines).strip()
            })

        return {
            "sections": sections,
            "raw":      text,
        }