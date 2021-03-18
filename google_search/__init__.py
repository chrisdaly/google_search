from .google_search import *

from bs4 import BeautifulSoup


def get_all_data(query: str, params: dict, query_id: int) -> list:
    start = 0
    params.update({"start": start})

    data = []
    while True:
        data_ = get_data(query, params, query_id)
        if data_:
            start = params.get("start")
            file_path = f"./{query_id}_{start}.html"
            # dump_data(html.encode("utf8")))

            start += 100
            params.update({"start": start})
            data.extend(data_)
        else:
            break

    return data


def get_data(query: str, params: dict, query_id: int, html: str = None) -> list:
    if not html:
        google_search = GoogleSearch(params)
        html = google_search.get_html(query)

    soup = BeautifulSoup(html, features="html.parser")
    start = params.get('start')
    google_page = GooglePage(soup, query_id=query_id, start=start)
    data = list(google_page.results())
    return data


def dump_data(data, directory):
    with open(directory, "w") as f:
        json.dump(data, f)


def download_image(string: str, file_path: str):
    if string:
        if "base64" in string:
            string = string.split('base64,')[1]

        image_data = base64.decodebytes(string.encode("ascii"))
        with open(file_path, 'wb') as f:
            f.write(image_data)
