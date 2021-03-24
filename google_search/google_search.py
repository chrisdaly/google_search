import re
import time
import requests
import datetime
import unicodedata
import unidecode
import dateutil.parser
import codecs

# from random import randint
from retry_decorator import retry
import json
import pandas as pd
import dateparser
from bs4 import BeautifulSoup


class RateLimitError(Exception):
    pass


class GoogleSearch:
    '''
        Docs: https://developers.google.com/custom-search/docs/xml_results#wsInterfaceLanguages
        hl: host language - improves overall quality of search: https://sites.google.com/site/tomihasa/google-language-codes
        gl: geolocation - boosts documents writtern in a specific country: https://developers.google.com/custom-search/docs/xml_results_appendices#countryCodes
        lr: language restrict - restrict to documents written in a specific language: https://developers.google.com/custom-search/docs/xml_results#wsInterfaceLanguages
        cr: country restrict - restrict to docmuents originating in a specific country: https://developers.google.com/custom-search/docs/xml_results_appendices#countryCollections
    '''

    def __init__(self, params):
        self.params = params
        self.urls = ['http://www.google.com/search', 'https://www.google.com/search']
        self.headers = {
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.106 Safari/537.36'}
        self.counter = 0

    @retry(RateLimitError, tries=5, timeout_secs=60)
    def get_html(self, query):
        counter = self.counter % 2
        url = self.urls[counter]
        headers = self.headers  # [counter]
        params = self.params.copy()
        params.update({'q': query})
        response = requests.get(url, params=params, headers=headers)
        print('\t', response.url)
        status_code = response.status_code
        print('\t', status_code, response, url)

        if response.ok:
            return response.text
        else:
            self.counter += 1
            if status_code == 429:
                print(response.url)
                raise RateLimitError('Ratelimit surpassed')
            else:
                raise Exception('Forbidden')


# def load_json_from_folder_into_df(dir_folder: str) -> pd.DataFrame:
#     files = os.listdir(dir_folder)

#     data = []
#     for file in tqdm.tqdm_notebook(files):
#         with open(f"{dir_folder}/{file}", "r") as f:
#             data_ = json.loads(f.read())
#             data.extend(data_)

#     df = pd.DataFrame(data)

#     return df


class GooglePage:
    def __init__(self, soup: str, query_id: int, start: int):
        self.soup = soup
        self.date_crawled = datetime.datetime.today()
        self.counter = 0
        self.query_id = query_id
        self.start = start

    @property
    def query(self):
        title = self.soup.title
        if title is not None:
            text = title.get_text().split('- ')[:-1]
            query = ''.join(text)
            return query

    @property
    def results_count(self):
        stats = self.soup.find('div', id='resultStats')
        if stats is not None:
            text = stats.get_text().strip()
            m = re.findall(r'((?:\d+[,\.])*\d+)', text)
            text = m[0].replace(",", "").replace('.', '')
            text = unicodedata.normalize("NFKD", text)
            results_count = int(text)
            return results_count

    @property
    def results_containers(self):
        container = self.soup.find('div', id='search')
        if container is not None:
            result_containers = container.find_all("g-card")
            return result_containers

    @property
    def image_mapping(self) -> dict:
        scripts = [x.get_text() for x in self.soup.find_all("script")]
        scripts = [x for x in scripts if x.startswith("(function(){var s='data:image/jpeg;base64")]

        mapping = {}
        for script in scripts:
            placeholder_ids = script.split(";var ii=")[1].split(";")[0].replace("'", '"')
            placeholder_ids = json.loads(placeholder_ids)
            real_src = script.split("(function(){var s='")[1].split("';var ii")[0]
            real_src = codecs.decode(real_src, 'unicode_escape')

            mapping_ = {id_: real_src for id_ in placeholder_ids}
            mapping.update(mapping_)

        return mapping

    @property
    def next_page(self):
        try:
            anchor = self.soup.find("a", {"id": "pnnext"})
            link = anchor.get("href")
            splitted = link.split("?")[1].split("&")
            start_param = [x for x in splitted if "start" in x][0]
            start = start_param.split("=")[1]
            return start

        except Exception as e:
            print(e)

    def results(self) -> list:
        query = self.query
        query_id = self.query_id
        date_crawled = self.date_crawled
        image_mapping = self.image_mapping
        print("image_mapping", len(image_mapping))

        if not self.results_containers:
            return []

        l = []
        for i, result_soup in enumerate(self.results_containers):
            search_position = str(i+1+self.start)
            google_result = GoogleResult(result_soup, search_position=search_position, query=query,
                                         query_id=query_id, date_crawled=date_crawled).parse()
            google_result["image"] = image_mapping.get(google_result["image_id"])

            l.append(google_result)

        return l

    def videos(self):
        video_heading = self.soup.find_all(lambda x: x.name == "h3" and x.get_text() == "Videos")
        if video_heading:
            return video_heading[0].parent.parent


class GoogleResult:
    def __init__(self, soup, search_position=None, query=None, query_id=None, date_crawled=None):
        self.soup = soup
        self.search_position = search_position
        self.query = query
        self.query_id = query_id
        self.date_crawled = date_crawled

    @property
    def id(self):
        if self.query_id:
            id_ = "{}{}{}".format(int(self.date_crawled.timestamp()), self.query_id, self.search_position)  # Should be unique with single thread
            return id_

    @property
    def title(self):
        title_ = self.soup.find('h3') or self.soup.find("div", {'role': 'heading'})
        if title_ is not None:
            title = title_.get_text().strip()
            title = unicodedata.normalize("NFKD", title)
            return title

    @property
    def link(self):
        div = self.soup.find('div', class_='r')
        if div is not None:
            link = div.a.get('href')
            if link.startswith('/url?'):
                link = link.split('/url?q=')[1]
                return link

        anchor = self.soup.find("a", {"style": "text-decoration:none;display:block"})  # news result
        if anchor is not None:
            link = anchor.get("href")
            return link

    @property
    def website(self):
        citation = self.soup.find("cite")
        if citation:
            website = citation.get_text().split("›")[0]
            return website

        images = self.soup.find_all("g-img")
        if len(images) == 2:
            website = images[1].parent.get_text()
            return website

    @property
    def description(self):
        description_ = self.soup.find('span', class_='st')

        sibling = self.soup.find("div", {"role": "heading"})
        if sibling is not None:
            description_ = list(sibling.parent.children)[-1]

        if description_:
            description = description_.get_text()
            description = unicodedata.normalize("NFKD", description)
            return description

    @property
    def keywords_matched(self):
        description_text = self.soup.find('span', class_='st')
        if description_text:
            keywords_matched = description_text.find_all('em')
            keywords_matched = list(set([x.get_text().lower() for x in keywords_matched]))
            return keywords_matched

    @property
    def image_id(self):
        section = self.soup.find("g-img")
        if section:
            image_id = section.img.get("id")
            return image_id
            # print("image_id", image_id)
            # if image_id:
            #     image = self.image_mapping.get("image_id")
            #     print("image", image)
            #     return image

    @property
    def date(self):
        spans = self.soup.find_all("span")
        if len(spans) > 0:
            date_description = spans[-1].get_text()
            return date_description
            # try:
            #     date = GoogleResult.format_date(date_description)
            #     return date
            # except Exception as e:
            #     print(e)

    @staticmethod
    def clean_text(text):
        if text is not None and isinstance(text, str):
            cleaned = ' '.join(unidecode.unidecode(text).split()).strip()
            return cleaned
        return text

    def parse(self):
        data = {
            'id': self.id,
            'title': self.title,
            'link': self.link,
            'website': self.website,
            'description': self.description,
            'search_position': self.search_position,
            'query': self.query,
            'query_id': self.query_id,
            'keywords_matched': self.keywords_matched,
            "image_id": self.image_id,
            "date": self.date,
            'date_crawled': self.date_crawled,
        }

        for k, v in data.items():
            data[k] = GoogleResult.clean_text(v)

        return data

    @staticmethod
    def date_text_to_datetime(text):
        if '-' in text:
            text = text.split('- ')[1]
        if 'ago' in text:
            amount, measure = text.replace(' ago', '').split()
            if not measure.endswith('s'):
                measure += 's'
            delta = {measure: int(amount)}
            date_published = datetime.datetime.today() - datetime.timedelta(**delta)
        else:
            date_published = dateutil.parser.parse(text)
        return date_published
