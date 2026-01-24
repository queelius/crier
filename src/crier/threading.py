"""Thread splitting logic for social media platforms."""

import re
from dataclasses import dataclass


@dataclass
class ThreadConfig:
    """Configuration for thread generation."""

    max_length: int = 280  # Default Twitter/Bluesky limit
    style: str = "numbered"  # numbered, simple, emoji
    max_posts: int = 25  # Maximum posts in a thread


def split_into_thread(
    content: str,
    max_length: int = 280,
    style: str = "numbered",
    max_posts: int = 25,
) -> list[str]:
    """Split content into a thread of posts.

    Priority order for splitting:
    1. Manual markers: <!-- thread --> in content
    2. Paragraph boundaries (double newline)
    3. Sentence boundaries (if paragraph too long)

    Args:
        content: The full content to split
        max_length: Maximum characters per post
        style: Thread style (numbered, simple, emoji)
        max_posts: Maximum number of posts in the thread

    Returns:
        List of post strings ready for publishing
    """
    # Strip and normalize whitespace
    content = content.strip()

    # 1. Check for manual markers
    if "<!-- thread -->" in content:
        parts = [p.strip() for p in content.split("<!-- thread -->") if p.strip()]
        return format_thread(parts, style, max_length, max_posts)

    # 2. Split by paragraphs
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]

    posts = []
    current = ""

    for para in paragraphs:
        # Calculate how much space we need for this paragraph
        if current:
            combined = current + "\n\n" + para
        else:
            combined = para

        # Check if combining would exceed limit (accounting for thread prefix later)
        # Reserve ~15 chars for prefix like "1/10\n\n" or "[emoji] 1/10\n\n"
        effective_limit = max_length - 15

        if len(combined) <= effective_limit:
            current = combined
        else:
            # Save current if non-empty
            if current:
                posts.append(current)

            # Handle oversized paragraph
            if len(para) > effective_limit:
                # Split by sentences
                sentence_parts = split_by_sentences(para, effective_limit)
                posts.extend(sentence_parts[:-1])  # Add all but last
                current = sentence_parts[-1] if sentence_parts else ""
            else:
                current = para

    # Don't forget the last chunk
    if current:
        posts.append(current)

    # Apply max_posts limit
    if len(posts) > max_posts:
        posts = posts[:max_posts]

    return format_thread(posts, style, max_length, max_posts)


def split_by_sentences(text: str, max_length: int) -> list[str]:
    """Split text by sentence boundaries when it's too long.

    Args:
        text: Text to split
        max_length: Maximum length per chunk

    Returns:
        List of text chunks, each under max_length
    """
    # Sentence-ending patterns
    sentence_pattern = r"(?<=[.!?])\s+"

    sentences = re.split(sentence_pattern, text)
    chunks = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if current:
            combined = current + " " + sentence
        else:
            combined = sentence

        if len(combined) <= max_length:
            current = combined
        else:
            # Save current if non-empty
            if current:
                chunks.append(current)

            # Handle oversized sentence
            if len(sentence) > max_length:
                # Last resort: split by words
                word_chunks = split_by_words(sentence, max_length)
                chunks.extend(word_chunks[:-1])
                current = word_chunks[-1] if word_chunks else ""
            else:
                current = sentence

    if current:
        chunks.append(current)

    return chunks


def split_by_words(text: str, max_length: int) -> list[str]:
    """Split text by word boundaries (last resort).

    Args:
        text: Text to split
        max_length: Maximum length per chunk

    Returns:
        List of text chunks
    """
    words = text.split()
    chunks = []
    current = ""

    for word in words:
        if current:
            combined = current + " " + word
        else:
            combined = word

        if len(combined) <= max_length:
            current = combined
        else:
            if current:
                chunks.append(current)
            # Handle oversized word (rare, but possible)
            if len(word) > max_length:
                # Hard truncate
                chunks.append(word[:max_length - 3] + "...")
                current = ""
            else:
                current = word

    if current:
        chunks.append(current)

    return chunks


def format_thread(
    posts: list[str],
    style: str,
    max_length: int,
    max_posts: int,
) -> list[str]:
    """Add thread indicators to posts.

    Args:
        posts: List of post content
        style: Thread style (numbered, simple, emoji)
        max_length: Maximum characters per post
        max_posts: Maximum posts (for truncation)

    Returns:
        List of formatted posts with thread indicators
    """
    # Limit to max_posts
    posts = posts[:max_posts]
    total = len(posts)

    if total == 1:
        # Single post, no thread indicator needed
        # But still truncate if too long
        post = posts[0]
        if len(post) > max_length:
            post = post[:max_length - 3] + "..."
        return [post]

    result = []
    for i, post in enumerate(posts, 1):
        if style == "numbered":
            prefix = f"{i}/{total}\n\n"
        elif style == "emoji":
            prefix = f"\U0001f9f5 {i}/{total}\n\n"  # Thread emoji
        else:  # simple
            prefix = ""

        # Ensure post fits with prefix
        max_content = max_length - len(prefix)
        if len(post) > max_content:
            post = post[:max_content - 3] + "..."

        result.append(prefix + post)

    return result


def estimate_thread_count(content: str, max_length: int = 280) -> int:
    """Estimate how many posts a thread will need.

    Useful for preview/dry-run mode.

    Args:
        content: The content to thread
        max_length: Maximum characters per post

    Returns:
        Estimated number of posts
    """
    posts = split_into_thread(content, max_length, style="simple")
    return len(posts)
