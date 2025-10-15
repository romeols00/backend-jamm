# api/serializers_utils.py
class AbsoluteURLMixin:
    def build_abs_url(self, path_or_url: str | None) -> str | None:
        if not path_or_url:
            return None
        request = self.context.get("request") if hasattr(self, "context") else None
        if not request:
            # Fallback: ritorna così com’è (relative url). Il FE potrebbe pre-pendere la base.
            return path_or_url
        # Se è già assoluto, non lo tocchiamo
        if str(path_or_url).startswith(("http://", "https://")):
            return path_or_url
        return request.build_absolute_uri(path_or_url)
