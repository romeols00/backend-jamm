from rest_framework.pagination import PageNumberPagination

class SuggestedPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"     # es: ?page_size=50
    page_query_param = "page"               # es: ?page=2
    max_page_size = 100

class FriendsPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "friends_page_size"  # es: ?friends_page_size=24
    page_query_param = "friends_page"            # es: ?friends_page=2
    max_page_size = 100