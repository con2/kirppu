from . import mark_down


def main():
    text = """
# Heading

## Subheading

### Sub-subheading

- Un-ordered list item
  - Sub-item

1. Ordered list item

*emphasis*

**strong**

[Link title](https://...)

Email address: <email>email@example.org</email>

A glyph: <glyph volume-off />

<alertbox danger>Alert *text* content</alertbox>
    """
    print(mark_down(text))


main()
