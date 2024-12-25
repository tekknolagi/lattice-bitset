#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.

import argparse
import math
import operator
import sys
from enum import Enum
from functools import reduce
from typing import Dict, List, NamedTuple, Set, TextIO, Tuple

# This file is used to generate Jit/hir/type_generated.h. Jit/type.md is
# recommended reading before trying to understand or change anything in here.


class UnionSpec(NamedTuple):
    name: str
    components: List[str]


class Type(NamedTuple):
    name: str
    bits: int


# First, define all the basic types, which each get 1 bit in the main Type
# bitset.

# Basic types that can't be subtyped by users.
BASIC_FINAL_TYPES: List[str] = [
    "Array",
    "Bool",
    "Slice",
]

# Basic types that can be subtyped by users. These will be expanded into *User
# and *Exact variants.
BASIC_BASE_TYPES: List[str] = [
    "Int",
    "Str",
    "List",
]

BASIC_EXACT_TYPES: List[str] = [
    "ObjectExact",
    *[ty + "Exact" for ty in BASIC_BASE_TYPES],
]

BASIC_USER_TYPES: List[str] = [
    "ObjectUser",
    *[ty + "User" for ty in BASIC_BASE_TYPES],
]

BASIC_PYTYPES: List[str] = BASIC_FINAL_TYPES + BASIC_EXACT_TYPES + BASIC_USER_TYPES

BASIC_INT_TYPES: List[str] = [
    "CInt8",
    "CInt16",
    "CInt32",
    "CInt64",
]

BASIC_UINT_TYPES: List[str] = [
    "CUInt8",
    "CUInt16",
    "CUInt32",
    "CUInt64",
]

# Basic types that are either runtime-internal or only used in Static
# Python. None can be subtyped by user code.
BASIC_PRIMITIVE_TYPES: List[str] = [
    "CBool",
    *BASIC_INT_TYPES,
    *BASIC_UINT_TYPES,
    "CPtr",
    "CDouble",
    "Nullptr",
]

BASIC_TYPES: List[str] = BASIC_PYTYPES + BASIC_PRIMITIVE_TYPES


# Predefined unions that are exclusively Python types, and will have optional
# variants created.
PYTYPE_UNIONS: List[UnionSpec] = [
    UnionSpec("BuiltinExact", BASIC_FINAL_TYPES + BASIC_EXACT_TYPES),
    *[UnionSpec(ty, [ty + "User", ty + "Exact"]) for ty in BASIC_BASE_TYPES],
    UnionSpec("User", BASIC_USER_TYPES),
    UnionSpec("Object", BASIC_PYTYPES),
]

# Predefined unions that are not exclusively Python types, and have no
# optional variant created.
OTHER_UNIONS: List[UnionSpec] = [
    UnionSpec("Top", BASIC_TYPES),
    UnionSpec("Bottom", []),
    UnionSpec("Primitive", BASIC_PRIMITIVE_TYPES),
    UnionSpec("CSigned", BASIC_INT_TYPES),
    UnionSpec("CUnsigned", BASIC_UINT_TYPES),
    UnionSpec("CInt", BASIC_UINT_TYPES + BASIC_INT_TYPES),
]


HEADER1 = """// Copyright (c) Meta Platforms, Inc. and affiliates.

#pragma once

// This file is @"""

HEADER2 = """generated by generate_jit_type_h.py.
// Run 'make regen-jit' to update it.

namespace jit::hir {

// clang-format off
"""

FOOTER = """
// clang-format on

} // namespace jit::hir
"""


def assign_bits() -> Tuple[Dict[str, int], int]:
    """Create the bit patterns for all predefined types: basic types are given
    one bit each, then union types are constructed from the basic types.
    """
    bit_idx = 0
    bits = {}
    for ty in BASIC_TYPES:
        bits[ty] = 1 << bit_idx
        bit_idx += 1

    for ty, components in PYTYPE_UNIONS + OTHER_UNIONS:
        bits[ty] = reduce(operator.or_, [bits[t] for t in components], 0)

    return bits, bit_idx


def generate_types() -> Tuple[List[Type], int]:
    """Compute a list of all predefined Types and the number of bits in the main
    bitset.
    """
    types: List[Type] = []
    bits, num_bits = assign_bits()
    nullptr_bit: int = bits["Nullptr"]

    def append_opt(name: str, bits: int) -> None:
        types.append(Type(name, bits))
        types.append(Type("Opt" + name, bits | nullptr_bit))

    for ty in BASIC_PYTYPES + [p[0] for p in PYTYPE_UNIONS]:
        ty_bits = bits[ty]
        append_opt(ty, ty_bits)

    for ty in BASIC_PRIMITIVE_TYPES:
        types.append(Type(ty, bits[ty]))

    for ty, _ in OTHER_UNIONS:
        types.append(Type(ty, bits[ty]))

    return types, num_bits


def write_types(file: TextIO) -> None:
    types, num_bits = generate_types()
    types.sort(key=lambda t: t[0])
    max_ty_len = 0
    max_bits_len = 0
    for ty, bits in types:
        # +1 for ','
        max_ty_len = max(max_ty_len, len(ty) + 1)
        # +2 for '0x'
        max_bits_len = max(max_bits_len, math.ceil(math.log(bits + 1, 16)) + 2)

    file.write(HEADER1)
    file.write(HEADER2)

    file.write("\n")

    file.write("// For all types, call X(name, bits)\n")
    file.write("#define HIR_TYPES(X)")
    for ty, bits in types:
        ty_arg = ty + ","
        line = f"  X({ty_arg:{max_ty_len}} {bits:#0{max_bits_len}x}UL)"
        file.write(f" \\\n{line}")

    file.write("\n\n")

    file.write(f"constexpr size_t kNumTypeBits = {num_bits};\n")

    file.write(FOOTER)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate type_generated.h")
    parser.add_argument("output_file", help="Filename to write to.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with open(args.output_file, "w") as file:
        write_types(file)


if __name__ == "__main__":
    sys.exit(main())
