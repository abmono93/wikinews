import mwclient
import pickle
from datetime import date
from html.parser import HTMLParser

START_STATE = 0
SCAN_STATE = 1
READING_STATE = 2

TRIPLE_QUOTE = "\'''"
STAR_CHAR = '*'
BAR_CHAR = '|'

def parse_item_name(data):
    item_name = ''

    data = data.lstrip('[[')
    while not data.startswith(']]'):
        if data.startswith(BAR_CHAR):
            item_name = ''
        else:
            item_name += data[0]
        data = data[1:]
    data = data.lstrip(']]')

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

    def create_new_category(self, category_name):
        self.categories[category_name] = {}
        self._current_category_chain = [category_name]
    
    def parse_bullet_point(self, line):
        depth = 0
        subcategory = None
        news_item = None
        
        def is_just_more_categories(line):
            ans = True
            while len(line) and line.startswith(','):
                line = line[1:]
                line = line.strip()
                if line.startswith('[['):
                    line = line[line.find(']]') + 2:]
            if len(line):
                ans = False
            return ans

        def parse_category():
            nonlocal line, subcategory
            subcategory = ''
            while len(line):
                if not line.startswith('[['):
                    subcategory += line[0]
                    line = line[1:]
                else:
                    item_name, line = parse_item_name(line)
                    subcategory += item_name

        while line[0] == STAR_CHAR:
            depth += 1
            line = line[1:]
        line = line.strip()
        if line.endswith(')]'):
            news_item = NewsItem(line)
        else:
            parse_category()

        return subcategory, depth, news_item

    def set_subcategory(self, subcategory, depth):
        while len(self._current_category_chain) > depth:
            self._current_category_chain.pop(-1)
        parent = self.categories
        for category in self._current_category_chain:
            parent = parent[category]
        parent[subcategory] = {}
        self._current_category_chain.append(subcategory)

    def append_news_item(self, news_item):
        parent = self.categories
        for category in self._current_category_chain:
            parent = parent[category]
        parent[news_item.url] = news_item
    
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

    def stringify(self, categories, format_str='{text} {source} {url}\n'):
        news_str = str()
        def add_news_items(category):
            nonlocal news_str
            for item_or_category in category.values():
                if type(item_or_category) == NewsItem:
                    news_str += format_str.format(
                        text=item_or_category.text,
                        source=item_or_category.source,
                        url=item_or_category.url)
                else:
                    add_news_items(item_or_category)
        add_news_items(categories)
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
        self.text = ''
        self.url = ''
        self.source = ''
        self.raw_info = raw_info
        self.parse_raw_info(raw_info)

    def __str__(self):
        return self.raw_info

    def __repr__(self):
        return f"'{self.raw_info}'"

    def parse_raw_info(self, data):
        while len(data):
            if data.startswith('[['):
                item_name, data = parse_item_name(data)
                self.text += item_name
            elif data.startswith('['):
                self.parse_link(data)
                break
            else:
                self.text += data[0]
                data = data[1:]
        self.text = self.text.strip()

    def parse_link(self, link):
        link = link.lstrip('[')
        while not link.startswith(' ('):
            self.url += link[0]
            link = link[1:]
        link = link.lstrip(' (')
        while not link.startswith(')'):
            if not link.startswith("'"):
                self.source += link[0]
            link = link[1:]
        link = link.lstrip(')]')






