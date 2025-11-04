# This is an include file for the Mp3tag source.
# It likely contains helper functions for parsing JSON by ASIN.

[MpgTagParser]
...
json_select "product"
    json_select "asin"
    OutputTo "ASIN"
...

# This file is included for reference.
# The Python script 'audible_client.py' implements this
# parsing logic directly in its '_parse_product_json' method.
#
# This file is NOT executed by the Python script.