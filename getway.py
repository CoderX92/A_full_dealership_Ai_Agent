"""
This was a hybrid approach as we did have a good framework, 
an alternative to costly vision model training computation SAVING
"""

import requests
import json
import sys
from pathlib import Path

imgbb_api_key = os.environ.get['IMGBB_API_KEY']
searchapi_key= os.environ.get['SEARCHAPI_KEY']
imgbb_expiration  = 600
search_timeout = 30
def upload_and_search(image_path):
    """
    1. Verifies that image_path exists.
    2. Uploads it to ImgBB (expires after imgbb_expiration seconds).
    3. Performs a Google Lens search via searchapi.io.
    Prints out results or errors and exits with code 1 on failure.
    """
    # 1. Verify local EXISTS
    if not Path(image_path).exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    # 2. Upload to ImgBB with error handles
    try:
        with open(image_path, 'rb') as f:
            imgbb_response = requests.post(
                "https://api.imgbb.com/1/upload",
                params={'key': imgbb_api_key, 'expiration': imgbb_expiration},
                files={'image': (Path(image_path).name, f)}
            )
        imgbb_response.raise_for_status()
        imgbb_data = imgbb_response.json()

        if not imgbb_data.get('success'):
            raise ValueError(f"ImgBB upload failed: {imgbb_data.get('error', 'Unknown error')}")

        image_url = imgbb_data['data']['url']
        print(f"Image uploaded successfully: {image_url}")

    except Exception as e:
        print(f"ImgBB upload failed: {e}")
        sys.exit(1)

    # 3. Search with Google Lens
    try:
        search_params = {
            "engine": "google_lens",
            "url": image_url,
            "api_key": searchapi_key
        }

        search_response = requests.get(
            "https://www.searchapi.io/api/v1/search",
            params=search_params,
            timeout=search_timeout
        )
        search_response.raise_for_status()

        # Handle response
        try:
            results = search_response.json()
            print("Search results:")
            if 'visual_matches' in results:
                titles = [match['title'] for match in results['visual_matches']]
                print("Found visual matches:")
                top_ten = titles[:15]
                results = "found matches:\n" + "\n".join(f"{i+1}. {title}" for i, title in enumerate(top_ten))
            else:
                print("No visual matches found in results")
        except json.JSONDecodeError:
            print("Unexpected response format:")
            print(search_response.text[:1000])

    except requests.exceptions.RequestException as e:
        print(f"SearchAPI request failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
    return results


if __name__ == "__main__":
    image_path = 'arts/pic2.jpg'
    ed = upload_and_search(image_path)
#    print("------- printing ED")
#    print(ed)
