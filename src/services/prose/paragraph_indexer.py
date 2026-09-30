"""
Paragraph indexer for splitting prose into indexed blocks.
"""

from typing import List, Dict
import re

class ParagraphIndexer:
    """
    Splits text into paragraphs and assigns each a stable index.
    """

    def __init__(self, min_chars: int = 100, max_chars: int = 300):
        """
        Initialize the indexer with target character range per paragraph.
        Args:
            min_chars: Minimum characters per paragraph (before merging).
            max_chars: Maximum characters per paragraph (before splitting).
        """
        self.min_chars = min_chars
        self.max_chars = max_chars

    def index_paragraphs(self, text: str) -> List[Dict[str, any]]:
        """
        Split text into paragraphs, assign indices, and return list of dicts.
        Each dict contains: index, text, and character offsets start/end.
        Args:
            text: The full text to index.
        Returns:
            List of paragraph dictionaries with keys: 'index', 'text', 'start', 'end'.
        """
        if not text or not text.strip():
            return []

        # Split by blank lines (multiple newlines) and remove empty lines
        raw_paragraphs = re.split(r'\n\s*\n', text.strip())
        paragraphs = [p.strip() for p in raw_paragraphs if p.strip()]

        # Adjust paragraph boundaries to target size (optional, for now we keep as split)
        # For simplicity, we'll just use the split paragraphs and assign indices.
        # strip() で削られた先頭分をオフセットに加算する
        base = len(text) - len(text.lstrip())
        cursor = base
        indexed = []
        for i, para in enumerate(paragraphs):
            # 元テキスト上で貪欲に探す（見つからない場合は -1 = Step 5 のガード用）
            start = text.find(para, cursor)
            if start < 0:
                start = end = -1
            else:
                end = start + len(para)
                cursor = end
            indexed.append({
                'index': i,
                'text': para,
                'start': start,
                'end': end,
            })
        return indexed
