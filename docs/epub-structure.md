# EPUB Structure

EPUB is a ZIP archive with a small set of required files and conventions. It
usually contains XHTML chapters, a navigation document, a package manifest,
CSS, images, and other resources.

## EPUB As A ZIP Container

```text
book.epub
  |
  +-- mimetype
  |
  +-- META-INF/
  |     +-- container.xml
  |
  +-- OEBPS/                Common name; may also be EPUB/ or OPS/
        +-- content.opf
        +-- nav.xhtml
        +-- chapter1.xhtml
        +-- chapter2.xhtml
        +-- styles.css
        +-- images/
              +-- cover.png
```

## How The Reader Finds The Package File

```text
book.epub
  |
  +-- META-INF/container.xml
          |
          |  Points to the OPF package file
          v
      OEBPS/content.opf
```

`container.xml` tells the EPUB reader where the package document lives:

```xml
<rootfile full-path="OEBPS/content.opf"
          media-type="application/oebps-package+xml"/>
```

## The OPF Package File

`content.opf` is the central package file for the EPUB.

```text
content.opf
  |
  +-- metadata    Title, author, language, identifier
  |
  +-- manifest    File inventory: all resources in the book
  |
  +-- spine       Reading order: which documents are read as body content
```

Example:

```xml
<manifest>
  <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
  <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  <item id="css" href="styles.css" media-type="text/css"/>
</manifest>

<spine>
  <itemref idref="chapter1"/>
</spine>
```

## Manifest vs Spine

```text
manifest: files included in the book
------------------------------------
nav.xhtml
chapter1.xhtml
chapter2.xhtml
styles.css
cover.png

spine: body reading order
------------------------------------
chapter1.xhtml -> chapter2.xhtml
```

The important detail is that `nav.xhtml` is usually in the `manifest`, but it
is not always in the `spine`. A translator that only walks the `spine` can
translate the body while missing the table of contents.

## Navigation Document

`nav.xhtml` is the EPUB 3 navigation document. Readers use it to show the book
table of contents.

```text
nav.xhtml
  |
  +-- Table of Contents
        |
        +-- Chapter 1  -> chapter1.xhtml
        +-- Chapter 2  -> chapter2.xhtml
```

Example:

```html
<nav epub:type="toc">
  <ol>
    <li><a href="chapter1.xhtml">Chapter 1</a></li>
    <li><a href="chapter2.xhtml">Chapter 2</a></li>
  </ol>
</nav>
```

The translatable text is:

```text
Chapter 1
Chapter 2
```

The links must be preserved:

```text
chapter1.xhtml
chapter2.xhtml
```

## Translation Flow

```text
EPUB ZIP
  |
  +-- content.opf
  |      |
  |      +-- Read manifest
  |      +-- Read spine
  |
  +-- body XHTML
  |      |
  |      +-- Extract h1 / p / li / td / figcaption / a text
  |      +-- Translate text
  |      +-- Write translated text back into the same XHTML nodes
  |
  +-- nav.xhtml
         |
         +-- Extract table-of-contents link text
         +-- Translate text
         +-- Preserve href attributes
```

## Current Adapter Behavior

```text
parse EPUB
  |
  +-- spine XHTML blocks
  |
  +-- nav.xhtml blocks
  |
  v
DocumentBlock[]
  |
  v
TranslationChunk[]
  |
  v
LLM translate
  |
  v
restore translated text
  |
  v
export EPUB
  |
  +-- Replace chapter XHTML text
  +-- Replace nav.xhtml table-of-contents text
  +-- Preserve images, CSS, href/src attributes, and ZIP structure
```

In short:

```text
EPUB = ZIP + container.xml + content.opf + XHTML body + nav document + resources
```

The table-of-contents translation issue happened because `nav.xhtml` lives in
the `manifest` and is not necessarily part of the `spine`. The fix is to parse
body content from the `spine` and separately parse the navigation document from
the `manifest` entry marked with `properties="nav"`.
