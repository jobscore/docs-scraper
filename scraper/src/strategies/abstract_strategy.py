from lxml.cssselect import CSSSelector
import lxml
import re
import json
import html

"""
Abstract Strategy
"""


class AbstractStrategy:
    """
    Abstract Strategy
    """
    config = None

    def __init__(self, config):
        self.config = config
        AbstractStrategy.keep_tags = config.keep_tags

    @staticmethod
    def pprint(data):
        """Pretty print a JSON-like structure"""
        print(
            json.dumps(data, indent=2, sort_keys=True, separators=(',', ': ')))

    @staticmethod
    def get_body(response):
        try:
            body = response.body.decode(response.encoding)
            return body
        except (UnicodeError, ValueError, AttributeError):
            return response.body

    @staticmethod
    def get_dom(response):
        """Get the DOM representation of the webpage"""
        try:
            body = response.body.decode(response.encoding)
            result = lxml.html.fromstring(body)
        except (UnicodeError, ValueError, lxml.etree.ParserError):
            result = lxml.html.fromstring(response.body)
        return result

    def get_strip_chars(self, level, selectors):
        if selectors[level]['strip_chars'] is None:
            return self.config.strip_chars
        return selectors[level]['strip_chars']

    def get_selectors_set_key(self, url):
        selectors_key = 'default'

        if url is not None:
            for start_url in self.config.start_urls:
                if re.search(start_url['compiled_url'], url) is not None:
                    selectors_key = start_url['selectors_key']
                    break

        return selectors_key

    def get_selectors_set(self, url):
        selectors_key = self.get_selectors_set_key(url)

        if selectors_key not in self.config.selectors:
            return self.config.selectors['default']

        return self.config.selectors[selectors_key]

    def get_min_indexed_level_for_url(self, url):
        selectors_key = self.get_selectors_set_key(url)

        if selectors_key not in self.config.min_indexed_level:
            return self.config.min_indexed_level['default']

        return self.config.min_indexed_level[selectors_key]

    @staticmethod
    def itertext(node, level=None, selectors=None):
        tag = node.tag
        if not isinstance(tag, str) and tag is not None:
            return

        if AbstractStrategy.will_skip_node(node, level, selectors):
            return

        if node.text or node.tag == 'img' or node.tag == 'meta':
            node_attrs_to_keep = AbstractStrategy.get_allowed_node_attrs(node, level, selectors)

            text = ''

            if AbstractStrategy.use_meta_content(level, selectors):
                text = AbstractStrategy.get_meta_content(node)
            elif node.text is not None:
                text = node.text

            if node_attrs_to_keep is None:
                yield text
            else:
                node_attrs_str = ' '.join([f" {k}='{v}'" for k, v in node_attrs_to_keep])
                yield '<' + node.tag + node_attrs_str + '>' + text + '</' + node.tag + '>'
        for e in node:
            for s in AbstractStrategy.itertext(e, level, selectors):
                yield s
            if e.tail:
                yield e.tail

    @staticmethod
    def escape(text):
        """We don't want to escape every html, and there is no selector-level config for that (sigh)"""
        # text = html.escape(text)

        for tag in AbstractStrategy.keep_tags:
            opening_tag = "<" + tag + ">"
            closing_tag = "</" + tag + ">"
            text = text.replace(html.escape(opening_tag), opening_tag)
            text = text.replace(html.escape(closing_tag), closing_tag)

        text = text.replace('&amp;', '&')

        return text

    @staticmethod
    def get_text(element, strip_chars=None, level=None, selectors=None):
        """Return the text content of a DOM node"""
        text = element

        # Do not call text_content if not needed (Ex. xpath selector with text() doesn't return a node but a string)
        if not isinstance(text, str):
            text = ""
            for s in AbstractStrategy.itertext(element, level, selectors):
                text = text + " " + s

        # We call strip a first time for space, tab, newline, return and formfeed
        text = text.strip()
        # then one more time if with custom strip_chars if there is some
        if strip_chars is not None:
            text = text.strip(strip_chars)

        if len(text) == 0:
            return None

        return AbstractStrategy.escape(text)

    @staticmethod
    def get_text_from_nodes(elements, strip_chars=None, level=None, selectors=None):
        """
        Return the text content of a set of DOM nodes.
        elements can contain either an array of nodes or a custom data return from xpath
        (Example: integer in the case of a count)
        """

        if not isinstance(elements, list):
            return elements

        if len(elements) == 0:
            return None

        text = ' '.join(
            [AbstractStrategy.get_text(element, strip_chars, level, selectors) for element in
             elements
             if AbstractStrategy.get_text(element, strip_chars, level, selectors) is not None])

        if len(text) == 0:
            return None

        return AbstractStrategy.escape(text)

    @staticmethod
    def remove_from_dom(dom, exclude_selectors):
        """Remove any elements matching the selector from the DOM"""
        for selector in exclude_selectors:
            matches = CSSSelector(selector)(dom)
            if len(matches) == 0:
                continue

            for match in matches:
                match.drop_tree()

        return dom

    @staticmethod
    def elements_are_equals(el1, el2):
        """Checks if two elements are actually the same"""
        return el1.getroottree().getpath(el1) == el2.getroottree().getpath(el2)

    @staticmethod
    def get_classnames_to_skip(level, selectors):
        try:
            return selectors[level]['classname_exclude']
        except (TypeError, KeyError):
            return None

    @staticmethod
    def get_node_classname(node):
        try:
            return [x[1] for x in node.attrib.items() if x[0] == 'class'][0]
        except (TypeError, KeyError, IndexError):
            return ""

    @staticmethod
    def will_skip_node(node, level, selectors):
        """Skip node if it contains css class defined in classname_exclude array"""
        classnames_to_skip = AbstractStrategy.get_classnames_to_skip(level, selectors)

        if classnames_to_skip is None:
            return False

        node_classname_attr = AbstractStrategy.get_node_classname(node)

        return any(classname_to_skip in node_classname_attr for classname_to_skip in classnames_to_skip)

    @staticmethod
    def use_meta_content(level, selectors):
        uses_meta_content = False

        try:
            uses_meta_content = selectors[level]['meta_tag']
        except (TypeError, KeyError):
            uses_meta_content = False

        return uses_meta_content or False

    @staticmethod
    def get_meta_content(node):
        return node.attrib['content'] or ''

    @staticmethod
    def get_allowed_node_attrs(node, level, selectors):
        """
        Return node attributes matching selector keep_tags
        If keep_tags = [], selector is allowed, but without any additional attribute
        """
        allowed_tags_attrs = None

        try:
            allowed_tags_attrs = selectors[level]['keep_tags'][node.tag]
        except (TypeError, KeyError):
            allowed_tags_attrs = None

        if allowed_tags_attrs is None:
            return None

        return [value for value in node.attrib.items() if value[0] in allowed_tags_attrs]

    @staticmethod
    def get_level_weight(level):
        """
        Returns a numeric weight based on the level of the selector

        >>> self.get_level_weight('lvl0') = 100
        >>> self.get_level_weight('lvl3') = 70
        >>> self.get_level_weight('content') = 0
        """
        matches = re.match(r'lvl([0-9]*)', level)
        if matches:
            return 100 - int(matches.group(1)) * 10
        return 0
