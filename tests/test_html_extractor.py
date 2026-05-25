from __future__ import annotations

import unittest

from llm_translate.html_utils.extractor import HTMLContentExtractor
from llm_translate.html_utils.structure import HTMLStructureParser


class HTMLExtractorTest(unittest.TestCase):
    def test_astro_code_block_keeps_line_breaks(self) -> None:
        html = """
<html>
  <body>
    <article>
      <h1>Memory Notes</h1>
      <p>Before code.</p>
      <pre class="astro-code astro-code-themes github-light" data-language="python"><code><span class="line"><span>from datetime import datetime, timezone</span></span>
<span class="line"></span>
<span class="line"><span>def _today_iso_utc() -&gt; str:</span></span>
<span class="line"><span>    return datetime.now(timezone.utc).strftime("%Y-%m-%dT")</span></span></code></pre>
      <p>After code.</p>
    </article>
  </body>
</html>
"""
        extracted = HTMLContentExtractor().extract(html)

        self.assertIn("```python\nfrom datetime import datetime, timezone", extracted.text)
        self.assertIn("\ndef _today_iso_utc() -> str:\n", extracted.text)
        self.assertIn('    return datetime.now(timezone.utc).strftime("%Y-%m-%dT")\n```', extracted.text)
        self.assertNotIn("```python from datetime", extracted.text)

        blocks = HTMLStructureParser("p1").parse(extracted.text)
        code_blocks = [block for block in blocks if block.block_type == "code_block"]
        self.assertGreaterEqual(len(code_blocks), 1)
        self.assertTrue(all("\n" in block.source_text for block in code_blocks))
        self.assertTrue(all("```python from datetime" not in block.source_text for block in code_blocks))


if __name__ == "__main__":
    unittest.main()
