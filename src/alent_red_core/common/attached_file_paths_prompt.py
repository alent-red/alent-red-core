class AttachedFilePathsPrompt:
    """Renders a prompt text followed by its attached file paths block."""

    @staticmethod
    def render(
        text: str | None,
        attached_file_paths: list[str],
        prefix: str,
        separator: str,
    ) -> str | None:
        """Append the attached file paths to a text using the configured prefix and separator.

        Every path is preceded by the separator, so the block reads as a list. The same
        rendering serves user messages and agent prompts.

        Args:
            text: Base text or None.
            attached_file_paths: Paths to list after the text, possibly empty.
            prefix: Text inserted once before the list.
            separator: Text inserted before each path.

        Returns:
            The rendered text, or the base text unchanged when there is no path.
        """
        if not attached_file_paths:
            return text

        paths_block = "".join(f"{separator}{path}" for path in attached_file_paths)
        return f"{text or ''}{prefix}{paths_block}"
