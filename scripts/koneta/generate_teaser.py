"""
generate_teaser.py
4コマ漫画画像（16:9）の上半分（1〜2コマ目）を自動クロップして
assets/social/YYYY-MM-DD-<slug>-teaser.jpg を機械的に生成するスクリプト。
手動コピーによる「4コマ丸ごと誤配置事故」を根絶するための安全配管。
"""

import sys
import argparse
from pathlib import Path
from PIL import Image

def create_teaser(input_path: Path, output_path: Path | None = None) -> Path:
    if not input_path.exists():
        raise FileNotFoundError(f"Input image not found: {input_path}")
    
    im = Image.open(input_path)
    width, height = im.size
    
    # 4-panel 2x2 grid: Crop top half (Panels 1 and 2)
    crop_box = (0, 0, width, height // 2)
    teaser_im = im.crop(crop_box)
    
    if output_path is None:
        gitv_root = Path(r"C:\Users\sgtko\Documents\ProjectYure\workspaces\GITV")
        slug_name = input_path.stem
        output_path = gitv_root / "assets" / "social" / f"{slug_name}-teaser.jpg"
        
    output_path.parent.mkdir(parents=True, exist_ok=True)
    teaser_im.save(output_path, quality=95)
    print(f"✅ Teaser successfully generated: {output_path} (Size: {teaser_im.size})")
    return output_path

def main():
    parser = argparse.ArgumentParser(description="Auto-generate 2-panel teaser from 4-panel manga")
    parser.add_argument("image", type=Path, help="Path to 4-panel manga image")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output teaser path")
    args = parser.parse_args()
    
    create_teaser(args.image, args.output)

if __name__ == "__main__":
    main()
