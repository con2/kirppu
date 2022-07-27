# -*- coding: utf-8 -*-
import base64
import math
import typing

if typing.TYPE_CHECKING:
    import django.http

"""
Miscellaneous utility functions.
"""


def swap(number, i1, i2):
    """
    Swap given bits from number.

    :param number: A number
    :type number: int
    :param i1: Bit index
    :type i1: int
    :param i2: Bit index
    :type i2: int
    :return: A number with given bits swapped.
    :rtype: int

    >>> swap(0b101011, 1, 4) == 0b111001
    True

    """
    b1 = (1 << i1)
    b2 = (1 << i2)
    v1 = number & b1
    v2 = number & b2

    if v1 and v2 or not (v1 or v2):
        return number
    if v1:
        number ^= b1
        number |= b2
    else:
        number |= b1
        number ^= b2
    return number


def number_to_hex(number, width):
    """
    Return the hex string representation of the given number.

    :param number: Number to convert
    :type number: int

    :param width: Width of the result in bits
    :type width: int

    :return: The number as a hex string
    :rtype: str

    :raise OverflowError: If the number does not fit into the given width.

    >>> number_to_hex(0xC0FFEE, 24)
    'C0FFEE'
    >>> number_to_hex(0xC0FFEE, 30)
    '00C0FFEE'
    >>> number_to_hex(0xC0FFEE, 23)
    Traceback (most recent call last):
        ...
    OverflowError: 12648430 does not fit into 23 bits

    """
    if number >> width != 0:
        raise OverflowError(
            '{0} does not fit into {1} bits'.format(number, width)
        )
    return '{0:0{1}X}'.format(number, int(math.ceil(width / 4.0)))


def hex_to_number(hex_string):
    """
    Return a int representation of the encoding code.

    :param hex_string: Hex string to convert
    :type hex_string: str
    :return: The hex string as a number
    :type: int

    >>> hex_to_number('00F00D') == 0xF00D
    True

    """
    return int(hex_string, 16)


def b32_encode(ref, length=5):
    """
    Encode a number as a b32 string.

    :param ref: Number to encode
    :type ref: int
    :param length: Number of bytes to encode
    :type length: int
    :return: Base32 encoded string
    :rtype: str

    >>> b32_encode(567273340440)
    'DA7CAFEE'
    """
    part = bytearray(length)
    for i in range(length):
        symbol = (ref >> (8 * i)) & 0xFF
        part[i] = int(symbol)

    # Encode the byte string in base32
    return base64.b32encode(part).decode().rstrip("=")


def b32_decode(data, length=5):
    """
    Decode a b32 string as a number.

    :param data: Base32 encoded string.
    :type data: str
    :param length: Number of bytes in the string.
    :type length: int
    :return: The decoded number
    :rtype: int
    :raise TypeError: If the data is not valid

    >>> b32_decode("DA7CAFEE")
    567273340440
    """
    data += "=" * int((5 - (1 + (length - 1) % 5)) * 1.5)
    parts = base64.b32decode(data)

    assert len(parts) == length

    number = 0
    for i in range(length):
        number |= parts[i] << (i * 8)
    return number


def pack(fields, checksum_bits=0):
    """
    Pack numbers into a single number.

    Each element of `fields` is a pair of numbers specifying a single data
    field. The first element specifies the width (in bits) of the field.
    The second element of the pair specifies the actual data to pack.

    :param fields: The data fields and their widths
    :type fields: [(int, int)]

    :param checksum_bits: Length, in bits, of the checksum to append
    :type checksum_bits: int

    :return: Packed data
    :rtype: int

    :raise OverflowError: If some data does not fit into the specified width.

    >>> pack([(4, 15), (3, 7), (5, 0)]) == 0xFE0
    True
    >>> pack([(2, 5)])
    Traceback (most recent call last):
        ...
    OverflowError: 5 does not fit into 2 bits

    """
    result = 0

    for width, number in fields:
        if number >> width != 0:
            raise OverflowError(
                '{0} does not fit into {1} bits'.format(number, width)
            )
        result <<= width
        result |= number

    csum = checksum(result, checksum_bits)
    result <<= checksum_bits
    result |= csum
    return result


class InvalidChecksum(ValueError):
    pass


def unpack(data, fields, checksum_bits=0):
    """
    Unpack packed data.

    Each element of `fields` specifies the width a single data field.

    :param data: Packed data
    :type data: int

    :param fields: The widths of the data fields
    :type fields: [int]

    :param checksum_bits: Length of the checksum in bits
    :type checksum_bits: int

    :return: List of unpacked data fields
    :rtype: [int]

    :raise InvalidChecksum: If the checksum does not match the data.

    >>> widths = [12, 34, 56]
    >>> data = [78, 90, 12]
    >>> packed = pack(zip(widths, data), 34)
    >>> unpack(packed, widths, 34) == data
    True
    >>> try: unpack(packed + 1, widths, 34)
    ... except InvalidChecksum as e: pass
    >>> unpack(2, [3, 2, 1])
    [0, 1, 0]

    """
    csum = data & ((1 << checksum_bits) - 1)
    data >>= checksum_bits
    if csum != checksum(data, checksum_bits):
        raise InvalidChecksum()

    result = []

    for width in reversed(fields):
        extracted = data & ((1 << width) - 1)
        result.append(extracted)
        data >>= width
    result.reverse()
    return result


def checksum(number, bits=4):
    """
    Calculate the checksum of a number.

    The checksum of length N is formed by splitting the number into
    bitstrings of N bits and performing a bitwise exclusive or on them.

    :param number: Number to generate the check
    :type number: int

    :return: Checksum of the number
    :rtype: int

    >>> checksum(0)
    0
    >>> checksum(0xFFF)
    15
    >>> checksum(0b01100111, 2)
    1

    """
    if bits == 0:
        return 0

    mask = (1 << bits) - 1
    chk = 0
    while number > 0:
        chk ^= (number & mask)
        number >>= bits
    return chk & mask


if __name__ == '__main__':
    import doctest
    doctest.testmod()

T = typing.TypeVar("T")


def get_form(form: typing.Type[T], request, *args, **kwargs) -> T:
    """
    Get form instance that matches request type.

    :param form: Form type to instantiate.
    :param request: Request to read data, if POST request.
    :param args: Additional positional arguments to the form constructor.
    :param kwargs: Additional keyword arguments to the form constructor.
    :return: form instance.
    """
    if request.method == "POST":
        return form(request.POST, *args, **kwargs)
    else:
        return form(*args, **kwargs)


def get_query_dict(request: "django.http.HttpRequest") -> typing.Optional["django.http.QueryDict"]:
    if request.method == "GET":
        return request.GET
    elif request.method == "POST":
        return request.POST


def shorten_text(text, length=80, cut_on_dot=True):
    """
    Get excerpt of 'text' from beginning.
    The text may contain one extra character after given length.

    :param text: Text to shorten.
    :type text: unicode
    :param length: Length to cut the string.
    :type length: int
    :param cut_on_dot: If `True` (default), cutting will happen primarily on first dot.
    :type cut_on_dot: bool
    :return: Shortened text.
    :rtype: unicode
    """
    # Find out where to cut the text.
    dot = text.find(".") if cut_on_dot else -1
    if dot == -1:
        # No dot. Give result for whole string.
        dot = len(text)
    else:
        # Cut 2 chars after first dot, which should be at least 10 chars, but less or equal than the length of text.
        dot = min(max(dot + 2, 10), len(text))

    # Result cut may be at most 80 chars.
    dot = min(dot, length)
    result = text[0:dot]

    # If the text was cut, add ellipsis.
    if dot < len(text):
        result += u"…"
    return result


def first(a_list, predicate):
    """
    Find first item of `a_list` matching `predicate`.

    :param a_list: A list of items.
    :type a_list: list[T]
    :param predicate: Predicate function. When this returns `True`, the tested item is returned.
    :type predicate: callable
    :return: First matched item or `None` if none is found.
    :rtype T|None
    """
    for item in a_list:
        if predicate(item):
            return item
    return None
