from rest_framework.parsers import BaseParser

class RawPostParser(BaseParser):
    """0
    custom parser that returns the raw request body(bytes).
    Essential for stripe webhook signature verification.
    """
    
    media_type = '*/*'  # Matches any content type sent by stripe
    
    def parse(self, stream, media_type=None, parser_context=None):
        return stream.read()