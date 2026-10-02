"""Validate fictional fixtures before changing the local demo catalog."""
import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DemoProduct(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=80)
    category: Literal['keyboard', 'mouse']
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=160)
    price_minor: int = Field(strict=True, gt=0)
    connections: list[Literal['wired', 'bluetooth', 'receiver']] = Field(min_length=1)
    quiet: bool | None
    numpad: bool | None
    weight_g: int = Field(strict=True, gt=0)
    layout: str | None
    portable: bool
    gaming: bool
    color: Literal['cream', 'sage', 'ink', 'stone']
    note: str = Field(min_length=1)


class Catalog(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['demo']
    notice: str = Field(min_length=1)
    products: list[DemoProduct] = Field(min_length=1)

    @model_validator(mode='after')
    def unique_ids(self):
        ids = [item.id for item in self.products]
        if len(ids) != len(set(ids)):
            raise ValueError('商品版本 ID 不可重复')
        return self


def main():
    parser = argparse.ArgumentParser(description='只校验演示数据，不导入真实商品、不改库。')
    parser.add_argument('path', nargs='?', type=Path, default=Path(__file__).resolve().parents[1] / 'data/demo/catalog.json')
    args = parser.parse_args()
    catalog = Catalog.model_validate(json.loads(args.path.read_text(encoding='utf-8')))
    print(f'PASS: {len(catalog.products)} fictional demo variants validated.')


if __name__ == '__main__':
    main()
