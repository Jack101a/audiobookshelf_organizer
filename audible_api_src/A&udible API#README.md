# Mp3tag Source - README

This folder contains the original Mp3tag source script files used as the canonical reference for the Python organizer script.

**These files are not executed.**

They are included for two primary reasons:
1.  **URL Templates:** To preserve the exact API endpoints used for fetching product and search data.
2.  **Field Mapping:** To define the relationship between the Audible JSON response and the desired metadata fields.

## Field Mappings (JSON -> Metadata)

This list defines the canonical mapping used in `audible_client.py`.

| Metadata Field | JSON Path (example) | Mp3tag Field |
| :--- | :--- | :--- |
| ASIN | `product.asin` | `ASIN` |
| Title | `product.title` | `TITLE` |
| Subtitle | `product.subtitle` | `SUBTITLE` |
| Authors | `product.authors[].name` | `AUTHOR` |
| Narrators | `product.narrators[].name` | `NARRATOR` / `READER` |
| Series | `product.series[0].title` | `SERIES` |
| Series Part | `product.series[0].sequence` | `SERIES-PART` |
| Description | `product.publisher_summary` | `DESC` / `COMMENT` |
| Release Date | `product.release_date` | `RELEASETIME` |
| Year | (parsed from `release_date`) | `YEAR` |
| Rating | `product.ratings_summary.average_rating` | `RATING` |
| Cover URL | `product.product_images["1000"]` | (n/a - used for download) |
| Product URL | `https://www.audible.com/pd/{asin}` | `WWWAUDIOFILE` |