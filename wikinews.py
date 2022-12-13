import mwclient
from datetime import date
from html.parser import HTMLParser

START_STATE = 0
SCAN_STATE = 1
READING_STATE = 2

TRIPLE_QUOTE = "\'''"
STAR_CHAR = '*'
BAR_CHAR = '|'

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
        self.news[self._current_date] = DayOfNews(data)
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
    def __init__(self, raw_info):
        self.categories = {}
        self._raw_info = raw_info
        self._current_category_chain = []

    def create_new_category(self, category_name):
        self.categories[category_name] = {}
        self._current_category_chain = [category_name]
    
    def parse_bullet_point(self, line):
        depth = 0
        item_name = ''
        subcategory = None
        news_item = None

        def parse_item_name():
            nonlocal line, item_name
            item_name = ''
            line = line.lstrip('[[')
            while not line.startswith(']]'):
                if line.startswith(BAR_CHAR):
                    item_name = ''
                else: 
                    item_name += line[0]
                line = line[1:]
            line = line.lstrip(']]')
        
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
            nonlocal line, news_item, item_name, subcategory
            parse_item_name()
            if len(line) == 0 or is_just_more_categories(line):
                subcategory = item_name
            else:
                news_item = NewsItem(item_name)
                parse_news_item()

        def parse_link():
            nonlocal line, news_item
            line = line.lstrip('[')
            while not line.startswith(' ('):
                news_item.url += line[0]
                line = line[1:]
            line = line.lstrip(' (')
            while not line.startswith(')'):
                if not line.startswith("'"):
                    news_item.source += line[0]
                line = line[1:]
            line = line.lstrip(')]')

        def parse_news_item():
            nonlocal line, news_item
            while len(line):
                if line.startswith('[['):
                    parse_item_name()
                    news_item.text += item_name
                elif line.startswith('['):
                    parse_link()
                    return
                else:
                    news_item.text += line[0]
                    line = line[1:]


        while line[0] == STAR_CHAR:
            depth += 1
            line = line[1:]
        line = line.strip()
        if line.startswith('[['):
            parse_category()
        else:
            news_item = NewsItem()
            parse_news_item()

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
  
class NewsItem():
    def __init__(self, text=None):
        self.text = text or ''
        self.url = ''
        self.source = ''





