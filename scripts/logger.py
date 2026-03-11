"""
Logging utilities for NotebookLM Skill
Handles saving query results and statistics to log files
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional


class QueryLogger:
    """Handles logging of NotebookLM query results"""

    def __init__(self, logs_dir: Path):
        """
        Initialize the logger with a logs directory

        Args:
            logs_dir: Path to the logs directory
        """
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(exist_ok=True)

    def _sanitize_filename(self, text: str, max_length: int = 50) -> str:
        """
        Sanitize text for use in filename

        Args:
            text: Text to sanitize
            max_length: Maximum length of result

        Returns:
            Sanitized filename-safe string
        """
        safe = "".join(
            c if c.isalnum() or c in (' ', '-', '_') else '_'
            for c in text
        )
        return safe[:max_length]

    def save_query_results(
        self,
        question: str,
        notebook_url: str,
        result: Dict[str, Optional[str]],
        use_markdown: bool = True
    ) -> Dict[str, Path]:
        """
        Save query results to log files

        Args:
            question: The question that was asked
            notebook_url: URL of the notebook used
            result: Dictionary with 'original', 'markdown', 'success' keys
            use_markdown: Whether markdown mode was enabled

        Returns:
            Dictionary mapping file type to saved file path
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_question = self._sanitize_filename(question)

        saved_files = {}

        # Always save original text
        original_file = self.logs_dir / f"{timestamp}_original_{safe_question}.txt"
        if result.get('original'):
            original_file.write_text(result['original'], encoding='utf-8')
            saved_files['original'] = original_file

        # Save markdown and stats if markdown was enabled and available
        if use_markdown and result.get('markdown'):
            markdown_file = self.logs_dir / f"{timestamp}_markdown_{safe_question}.md"
            markdown_file.write_text(result['markdown'], encoding='utf-8')
            saved_files['markdown'] = markdown_file

            # Save comparison statistics
            stats_file = self.logs_dir / f"{timestamp}_stats_{safe_question}.json"
            stats = {
                'question': question,
                'notebook_url': notebook_url,
                'original_length': len(result['original']) if result.get('original') else 0,
                'markdown_length': len(result['markdown']) if result.get('markdown') else 0,
                'ratio': (
                    len(result['markdown']) / len(result['original'])
                    if result.get('original') and result.get('markdown') else 0
                ),
                'timestamp': timestamp,
                'has_markdown': True
            }
            stats_file.write_text(
                json.dumps(stats, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            saved_files['stats'] = stats_file

        # Save stats indicating markdown failed if enabled but not available
        elif use_markdown:
            stats_file = self.logs_dir / f"{timestamp}_stats_{safe_question}.json"
            stats = {
                'question': question,
                'notebook_url': notebook_url,
                'original_length': len(result['original']) if result.get('original') else 0,
                'markdown_length': 0,
                'ratio': 0,
                'timestamp': timestamp,
                'has_markdown': False,
                'reason': 'Copy button failed or response too short'
            }
            stats_file.write_text(
                json.dumps(stats, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            saved_files['stats'] = stats_file

        return saved_files

    def print_save_summary(self, saved_files: Dict[str, Path]):
        """
        Print a summary of saved files

        Args:
            saved_files: Dictionary mapping file type to saved file path
        """
        for file_type, file_path in saved_files.items():
            label = {
                'original': 'original output',
                'markdown': 'markdown output',
                'stats': 'comparison stats'
            }.get(file_type, file_type)
            print(f"💾 Saved {label} to: {file_path}")
