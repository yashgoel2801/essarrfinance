import os
from PIL import Image
import sys

def compress_images(directory, quality=70, max_width=1200):
    """
    Recursively walk through directory and compress all images found.
    """
    supported_formats = ('.jpg', '.jpeg', '.png')
    total_files = 0
    compressed_files = 0
    total_saved = 0

    print(f"Starting compression in: {directory}")
    print(f"Target Quality: {quality}%, Max Width: {max_width}px\n")

    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(supported_formats):
                total_files += 1
                file_path = os.path.join(root, file)
                
                try:
                    original_size = os.path.getsize(file_path)
                    
                    with Image.open(file_path) as img:
                        # Skip if already small enough (optional, but good for speed)
                        # We compress regardless to ensure 70% quality consistentcy
                        
                        # Convert to RGB
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        
                        # Resize if too large
                        original_width, original_height = img.size
                        if original_width > max_width:
                            new_height = int((max_width / original_width) * original_height)
                            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                        
                        # Save back to same path as JPEG
                        # If it was PNG, we replace it with JPG extension? 
                        # To avoid breaking DB links, we keep SAME filename but overwrite content
                        # Even if it's a PNG on disk, we can save JPEG data into it (standard apps handle this)
                        # BUT more safely, we keep original format if it's already JPG.
                        
                        file_ext = os.path.splitext(file)[1].lower()
                        save_format = 'JPEG' if file_ext in ('.jpg', '.jpeg') else 'PNG'
                        
                        if save_format == 'JPEG':
                            img.save(file_path, format='JPEG', quality=quality, optimize=True)
                        else:
                            # For PNG, optimize without quality loss (as PNG is lossless)
                            img.save(file_path, format='PNG', optimize=True)
                    
                    new_size = os.path.getsize(file_path)
                    saved = original_size - new_size
                    total_saved += saved
                    compressed_files += 1
                    
                    if saved > 0:
                        print(f"[OK] {file}: {original_size/1024:.1f}KB -> {new_size/1024:.1f}KB (Saved {saved/1024:.1f}KB)")
                    else:
                        print(f"[-] {file}: No reduction possible.")

                except Exception as e:
                    print(f"[ERROR] Could not process {file}: {e}")

    print(f"\nSummary:")
    print(f"Total images found: {total_files}")
    print(f"Images processed: {compressed_files}")
    print(f"Total space saved: {total_saved / (1024*1024):.2f} MB")

if __name__ == "__main__":
    # Use current directory/media if not specified
    media_dir = os.path.join(os.getcwd(), 'media')
    if len(sys.argv) > 1:
        media_dir = sys.argv[1]
    
    if os.path.exists(media_dir):
        compress_images(media_dir)
    else:
        print(f"Error: Directory {media_dir} not found.")
