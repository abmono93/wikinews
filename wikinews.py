import mwclient
import pickle
from datetime import date
from html.parser import HTMLParser

START_STATE = 0
SCAN_STATE = 1
READING_STATE = 2

SINGLE_QUOTE = "'"
TRIPLE_QUOTE = "\'''"
STAR_CHAR = '*'
BAR_CHAR = '|'
SQUARE_OPEN_BRACKET = '['
CLOSE_PAREN = ')'
OPEN_BRACKETS = '[['
CLOSE_BRACKETS = ']]'

def consume(_string):
    return _string[0], _string[1:]

def parse_item_name(data):
    item_name = str()

    data = data.lstrip(OPEN_BRACKETS)
    while not data.startswith(CLOSE_BRACKETS):
        first_char, data = consume(data)
        if first_char == BAR_CHAR:
            item_name = str()
        else:
            item_name += first_char
    data = data.lstrip(CLOSE_BRACKETS)

    return item_name, data

class WikiNewsGenerator(HTMLParser):
    def __init__(self):
        super(). __init__() 
        self.news = {}
        self._current_date = None
        self._state = START_STATE
        self._fill_news()

    def _fill_news(self):
        site = mwclient.Site('en.wikipedia.org')
        current_events_text = site.pages['Portal:Current_events'].text(expandtemplates=True)
        self.feed(current_events_text)
    
    def _change_date(self, data):
        try:
            new_date = date.fromisoformat(data)
        except ValueError:
            return False
        self._current_date = new_date
        self._state = SCAN_STATE
        return True

    def _scan_to_info(self, tag):
        if tag == 'nowiki':
            self._state = READING_STATE

    def _read_info(self, data):
        if len(data) > 2:
            self.news[self._current_date] = DayOfNews(self._current_date, data)
        self._state = START_STATE

    def handle_endtag(self, tag):
        if self._state == SCAN_STATE:
            self._scan_to_info(tag)

    def handle_data(self, data):
        if self._change_date(data) or self._state == START_STATE:
            return

        if self._state == READING_STATE:
            self._read_info(data)

class DayOfNews():
    def __init__(self, date, raw_info):
        self.date = date
        self.categories = {}
        self._raw_info = raw_info
        self._current_category_chain = []
        self.parse_info()

    def get_current_category(self):
        current_category = self.categories

        for category in self._current_category_chain:
            current_category = current_category[category]

        return current_category

    def create_new_category(self, category_name):
        self.categories[category_name] = {}
        self._current_category_chain = [category_name]
    
    def parse_bullet_point(self, line):
        depth = 0
        subcategory = None
        news_item = None

        def _parse_category(raw_category):
            subcategory = str()

            while len(raw_category):
                if not raw_category.startswith(OPEN_BRACKETS):
                    first_char, raw_category = consume(raw_category)
                    subcategory += first_char
                else:
                    item_name, raw_category = parse_item_name(raw_category)
                    subcategory += item_name

            return subcategory

        while line.startswith(STAR_CHAR):
            depth += 1
            _, line = consume(line)
        line = line.strip()
        if line.endswith(')]'):
            news_item = NewsItem(line)
        else:
            subcategory = _parse_category(line)

        return subcategory, depth, news_item

    def set_subcategory(self, subcategory, depth):
        while len(self._current_category_chain) > depth:
            self._current_category_chain.pop(-1)
        self.get_current_category()[subcategory] = {}
        self._current_category_chain.append(subcategory)

    def append_news_item(self, news_item):
        self.get_current_category()[news_item.url] = news_item
    
    def parse_info(self):
        for line in self._raw_info.splitlines():
            if line.startswith(TRIPLE_QUOTE):
                self.create_new_category(line.strip(TRIPLE_QUOTE))
            elif line.startswith(STAR_CHAR):
                subcategory, depth, news_item = self.parse_bullet_point(line)
                if subcategory:
                    self.set_subcategory(subcategory, depth)
                elif news_item:
                    self.append_news_item(news_item)

    def stringify(self, categories=None, format_str='{text} {source} {url}\n'):
        news_str = str()

        def add_news_items(category):
            nonlocal news_str
            for item_or_category in category.values():
                if type(item_or_category) == NewsItem:
                    news_str += format_str.format(
                        text=item_or_category.text,
                        source=item_or_category.source,
                        url=item_or_category.url,
                        date=self.date)
                else:
                    add_news_items(item_or_category)
        add_news_items(categories or self.categories)

        return news_str

    def write_to_file(self):
        with open(f'{self.date}', 'wb') as f:
            pickle.dump(self, file=f)

    def get_urls(self):
        urls = []

        def _get_urls_in(category):
            nonlocal urls
            for value in category.values():
                if type(value) != NewsItem:
                    _get_urls_in(value)
                else:
                    urls.append(value.url)
        _get_urls_in(self.categories)

        return urls

    def remove_duplicates(self, other_dayofnews=None, url_list=None):

        def _remove_duplicates_from_category(remove, duplicates):
            for key, value in duplicates.items():
                if type(value) == NewsItem:
                    if value.url in remove.keys():
                        remove.pop(value.url)
                elif key in remove:
                    _remove_duplicates_from_category(
                        remove[key],
                        duplicates[key])

        def _remove_duplicate_urls(remove, urls):
            to_delete = []
            for value in remove.values():
                if type(value) == NewsItem:
                    if value.url in urls:
                        to_delete.append(value.url)
                else:
                    _remove_duplicate_urls(
                        value,
                        urls)
            for url in to_delete:
                remove.pop(url)

        def _remove_empty_categories(categories):
            to_delete = []
            for key, value in categories.items():
                if type(value) != NewsItem:
                    _remove_empty_categories(value)
                    if len(value) == 0:
                        to_delete.append(key)
            for key in to_delete:
                categories.pop(key)

        if other_dayofnews:
            _remove_duplicates_from_category(self.categories, other_dayofnews.categories)
        elif url_list:
            _remove_duplicate_urls(self.categories, url_list)
        _remove_empty_categories(self.categories)

class NewsItem():
    def __init__(self, raw_info):
        self.text = str()
        self.url = str()
        self.source = str()
        self.raw_info = raw_info
        self.parse_raw_info(raw_info)

    def __str__(self):
        return self.raw_info

    def __repr__(self):
        return f"'{self.raw_info}'"

    def parse_raw_info(self, data):
        while len(data):
            if data.startswith(OPEN_BRACKETS):
                item_name, data = parse_item_name(data)
                self.text += item_name
            elif data.startswith(SQUARE_OPEN_BRACKET):
                self.parse_link(data)
                break
            else:
                first_char, data = consume(data)
                self.text += first_char
        self.text = self.text.strip()

    def parse_link(self, link):
        link = link.lstrip(SQUARE_OPEN_BRACKET)
        while not link.startswith(' ('):
            first_char, link = consume(link)
            self.url += first_char
        link = link.lstrip(' (')
        while not link.startswith(CLOSE_PAREN):
            first_char, link = consume(link)
            if first_char != SINGLE_QUOTE:
                self.source += first_char
        link = link.lstrip(')]')