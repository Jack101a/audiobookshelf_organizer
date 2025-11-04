# This is a main include file for the Mp3tag source.
# It defines common JSON parsing logic used by all scripts.

[MpgTagParser]
...
# Example of field mapping:
json_select "title"
OutputTo "TITLE"

json_select "authors"
    json_select_many "name"
    JoinUsing " & "
OutputTo "AUTHOR"

json_select "narrators"
    json_select_many "name"
    JoinUsing " & "
OutputTo "NARRATOR"
...

# This file is included for reference.
# The Python script 'audible_client.py' implements this
# parsing logic directly in its '_parse_product_json' method.
#
# This file is NOT executed by the Python script.