#!/usr/bin/env python3
"""
Source Filter for NotebookLM
Determines which sources are relevant to a query and handles source selection in browser

Supports two modes:
1. Keyword matching (fast, no API calls)
2. LLM scoring via Gemini (smarter, understands semantics)
"""

import re
import sys
import json
import subprocess
import traceback
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config import SOURCE_SUMMARY_DIR


class SourceFilter:
    """Handles source relevance detection and selection"""

    def __init__(self, notebook_id: str):
        """
        Initialize source filter for a notebook

        Args:
            notebook_id: ID of the notebook
        """
        self.notebook_id = notebook_id
        self.sources = self._load_sources()

    def _load_sources(self) -> List[Dict[str, str]]:
        """Load sources from the summary file"""
        summary_path = SOURCE_SUMMARY_DIR / f"{self.notebook_id}.md"
        sources = []

        if not summary_path.exists():
            print(f"  ⚠️ No source summary file found for: {self.notebook_id}")
            return sources

        try:
            with open(summary_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse sources from markdown
            current_title = None
            current_summary_lines = []

            for line in content.split('\n'):
                if line.startswith('### '):
                    # Save previous source
                    if current_title:
                        sources.append({
                            'title': current_title,
                            'summary': '\n'.join(current_summary_lines).strip()
                        })
                    current_title = line[4:].strip()
                    current_summary_lines = []
                elif line.startswith('---') or line.startswith('# ') or line.startswith('**'):
                    continue
                elif current_title:
                    current_summary_lines.append(line)

            # Don't forget the last one
            if current_title:
                sources.append({
                    'title': current_title,
                    'summary': '\n'.join(current_summary_lines).strip()
                })

            print(f"  📚 Loaded {len(sources)} sources for filtering")
            return sources

        except Exception as e:
            print(f"  ⚠️ Error loading sources: {e}")
            return []

    def get_relevant_sources(self, question: str, use_llm: bool = True, threshold: int = 5) -> List[str]:
        """
        Determine which sources are relevant to the question

        Args:
            question: The question to ask
            use_llm: If True, use Gemini for semantic scoring. If False, use keyword matching.
            threshold: Minimum relevance score (1-10) for LLM mode. Default 5.

        Returns:
            List of source titles that are relevant
        """
        if not self.sources:
            return []  # No filtering if no sources loaded

        if use_llm:
            return self._get_relevant_sources_llm(question, threshold)
        else:
            return self._get_relevant_sources_keywords(question)

    def _get_relevant_sources_llm(self, question: str, threshold: int = 5) -> List[str]:
        """Use LLM to score source relevance semantically.

        Fallback chain: Gemini CLI → Claude CLI → Keyword matching
        """
        print(f"  🤖 Using LLM to score source relevance (threshold: {threshold}/10)...")

        # Build prompt with source list
        source_list = "\n".join([
            f"{i+1}. **{s['title']}**: {s['summary'][:200]}..."
            for i, s in enumerate(self.sources)
        ])

        prompt = f"""Given this question: "{question}"

Rate how relevant each source is on a scale of 1-10:
- 10: Directly answers the question
- 7-9: Highly relevant, contains key information
- 4-6: Somewhat relevant, provides context
- 1-3: Not relevant to this question

Sources:
{source_list}

IMPORTANT: Respond ONLY with a JSON array of objects, each with "index" (1-based) and "score" (1-10).
Example: [{{"index": 1, "score": 8}}, {{"index": 2, "score": 3}}]

Be generous with scores - if a source MIGHT contain relevant information, give it at least 5.
Consider semantic relationships, not just keyword matches."""

        # Try Gemini first
        result = self._call_gemini(prompt)

        # If Gemini fails, try Claude
        if result is None:
            print(f"    → Trying Claude CLI...")
            result = self._call_claude(prompt)

        # If both fail, fall back to keywords
        if result is None:
            print(f"    → Falling back to keyword matching")
            return self._get_relevant_sources_keywords(question)

        # Parse and return results
        return self._parse_llm_scores(result, threshold)

    def _call_gemini(self, prompt: str) -> Optional[str]:
        """Call Gemini CLI and return response, or None on failure"""
        try:
            result = subprocess.run(
                ['gemini', '-m', 'gemini-2.0-flash', '-p', prompt],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            return None
        except FileNotFoundError:
            print(f"    ⚠️ Gemini CLI not installed")
            return None
        except subprocess.TimeoutExpired:
            print(f"    ⚠️ Gemini timeout")
            return None
        except Exception as e:
            print(f"    ⚠️ Gemini error: {e}")
            return None

    def _call_claude(self, prompt: str) -> Optional[str]:
        """Call Claude CLI and return response, or None on failure"""
        try:
            # Use claude CLI with -p for print mode (non-interactive)
            result = subprocess.run(
                ['claude', '-p', prompt, '--model', 'claude-sonnet-4-20250514'],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            return None
        except FileNotFoundError:
            print(f"    ⚠️ Claude CLI not installed")
            return None
        except subprocess.TimeoutExpired:
            print(f"    ⚠️ Claude timeout")
            return None
        except Exception as e:
            print(f"    ⚠️ Claude error: {e}")
            return None

    def _parse_llm_scores(self, output: str, threshold: int) -> List[str]:
        """Parse LLM response and return relevant source titles"""
        try:
            # Extract JSON from response (might have markdown code blocks)
            json_match = re.search(r'\[.*\]', output, re.DOTALL)
            if not json_match:
                print(f"    ⚠️ Could not find JSON in LLM response")
                return self._get_relevant_sources_keywords("")

            scores = json.loads(json_match.group())

            # Build results
            relevant = []
            for item in scores:
                idx = item.get('index', 0) - 1  # Convert to 0-based
                score = item.get('score', 0)

                if 0 <= idx < len(self.sources) and score >= threshold:
                    relevant.append({
                        'title': self.sources[idx]['title'],
                        'score': score
                    })

            # Sort by score
            relevant.sort(key=lambda x: x['score'], reverse=True)

            if relevant:
                print(f"  ✓ LLM selected {len(relevant)} relevant sources (out of {len(self.sources)})")
                for s in relevant[:5]:
                    print(f"    - {s['title'][:50]}... (score: {s['score']}/10)")
                if len(relevant) > 5:
                    print(f"    ... and {len(relevant) - 5} more")
                return [s['title'] for s in relevant]
            else:
                print(f"  ℹ️ No sources scored >= {threshold}, using all sources")
                return [s['title'] for s in self.sources]

        except json.JSONDecodeError as e:
            print(f"    ⚠️ JSON parse error: {e}")
            return [s['title'] for s in self.sources]
        except Exception as e:
            print(f"    ⚠️ Parse error: {e}")
            return [s['title'] for s in self.sources]

    def _get_relevant_sources_keywords(self, question: str) -> List[str]:
        """Use keyword matching for source relevance (fallback method)"""
        question_lower = question.lower()

        # Extract keywords from the question
        stop_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'what', 'who', 'when',
            'where', 'why', 'how', 'did', 'do', 'does', 'had', 'has', 'have',
            'this', 'that', 'these', 'those', 'it', 'its', 'in', 'on', 'at',
            'to', 'for', 'of', 'with', 'by', 'from', 'about', 'into', 'and',
            'or', 'but', 'if', 'then', 'so', 'as', 'be', 'been', 'being',
            'can', 'could', 'would', 'should', 'may', 'might', 'must', 'will',
            'me', 'my', 'your', 'his', 'her', 'their', 'our', 'please', 'tell',
            'explain', 'describe', 'give', 'list', 'show', 'find', 'answer'
        }

        words = re.findall(r'\b[a-zA-Z\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+\b', question_lower)
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        names = re.findall(r'\b[A-Z][a-zA-Z]+\b', question)
        keywords.extend([n.lower() for n in names])

        cjk_terms = re.findall(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+', question)
        keywords.extend(cjk_terms)

        keywords = list(set(keywords))

        print(f"  🔍 Keywords extracted: {keywords[:10]}{'...' if len(keywords) > 10 else ''}")

        relevant_sources = []

        for source in self.sources:
            title_lower = source['title'].lower()
            summary_lower = source['summary'].lower()
            combined_text = title_lower + ' ' + summary_lower

            score = 0
            matched_keywords = []

            for keyword in keywords:
                if keyword in combined_text:
                    if keyword in title_lower:
                        score += 3
                    else:
                        score += 1
                    matched_keywords.append(keyword)

            if score > 0:
                relevant_sources.append({
                    'title': source['title'],
                    'score': score,
                    'matched': matched_keywords
                })

        relevant_sources.sort(key=lambda x: x['score'], reverse=True)

        if relevant_sources:
            threshold = 1
            filtered = [s for s in relevant_sources if s['score'] >= threshold]

            print(f"  ✓ Found {len(filtered)} relevant sources (out of {len(self.sources)})")
            for s in filtered[:5]:
                print(f"    - {s['title'][:50]}... (score: {s['score']})")
            if len(filtered) > 5:
                print(f"    ... and {len(filtered) - 5} more")

            return [s['title'] for s in filtered]
        else:
            print(f"  ℹ️ No specific matches found, using all {len(self.sources)} sources")
            return [s['title'] for s in self.sources]

    def get_all_source_titles(self) -> List[str]:
        """Get all source titles"""
        return [s['title'] for s in self.sources]


def select_sources_in_browser(page, relevant_titles: List[str], all_titles: List[str]) -> bool:
    """
    Select only relevant sources in the NotebookLM browser UI

    Uses Playwright's native click for reliable checkbox interaction.

    Args:
        page: Playwright page object
        relevant_titles: List of source titles to SELECT (keep checked)
        all_titles: List of ALL source titles (to know what to deselect)

    Returns:
        True if selection was successful
    """
    import time
    from browser_utils import StealthUtils

    if not relevant_titles or not all_titles:
        print("  ℹ️ No source filtering needed")
        return True

    # If all sources are relevant, no need to filter
    if set(relevant_titles) == set(all_titles):
        print("  ℹ️ All sources are relevant, no filtering needed")
        return True

    titles_to_keep = set(relevant_titles)
    titles_to_deselect = set(all_titles) - titles_to_keep

    print(f"  🔧 Filtering sources: keeping {len(titles_to_keep)}, removing {len(titles_to_deselect)}")

    # Helper function to check if a title should be deselected
    def should_deselect(element_text: str) -> bool:
        text = element_text.lower().strip()
        for title in titles_to_deselect:
            t = title.lower()
            if text.find(t[:25]) >= 0 or t.find(text[:25]) >= 0:
                return True
        return False

    try:
        # Use Playwright's native selectors and clicks for reliable interaction
        # Find all source containers
        containers = page.query_selector_all('.single-source-container')
        print(f"    Found {len(containers)} source containers")

        deselected = 0
        errors = []

        for container in containers:
            try:
                # Get the text content of this source
                text = container.inner_text() or ""
                short_text = text[:40].replace('\n', ' ')

                # Check if this source should be deselected
                if not should_deselect(text):
                    continue

                # Find the checkbox
                checkbox = container.query_selector('mat-checkbox.select-checkbox')
                if not checkbox:
                    errors.append(f"No checkbox: {short_text}")
                    continue

                # Check if currently checked
                checkbox_class = checkbox.get_attribute('class') or ""
                if 'mat-mdc-checkbox-checked' not in checkbox_class:
                    print(f"      Already unchecked: {short_text}")
                    continue

                # Use Playwright's native click on the checkbox
                # This properly triggers Angular's change detection
                checkbox.click(force=True)
                StealthUtils.random_delay(100, 200)

                # Verify
                new_class = checkbox.get_attribute('class') or ""
                if 'mat-mdc-checkbox-checked' not in new_class:
                    print(f"      ✓ Unchecked: {short_text}")
                    deselected += 1
                else:
                    print(f"      ⚠ Click didn't work: {short_text}")

            except Exception as e:
                errors.append(f"Error: {str(e)[:50]}")
                continue

        if deselected > 0:
            print(f"    ✓ Successfully deselected {deselected} sources")
            StealthUtils.random_delay(300, 600)
        elif errors:
            for err in errors[:3]:
                print(f"      ⚠️ {err}")
        else:
            print(f"    ℹ️ No sources needed deselecting")

        return True

    except Exception as e:
        print(f"  ⚠️ Error filtering sources: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Test the filter
    import argparse

    parser = argparse.ArgumentParser(description='Test source filtering')
    parser.add_argument('--notebook-id', required=True, help='Notebook ID')
    parser.add_argument('--question', required=True, help='Question to analyze')

    args = parser.parse_args()

    filter = SourceFilter(args.notebook_id)
    relevant = filter.get_relevant_sources(args.question)

    print(f"\nRelevant sources for: {args.question}")
    for title in relevant:
        print(f"  - {title}")
