from django.urls import path
from .views import ActivateAccountView, EventiPerLocaleView, EventiView, EventoDetailView, FriendsAndSuggestedView, ListaEventiView, ListaLocaliView, ListaPersoneView, LocaleDetailView, LocalePrivacyView, LogoutView, PasswordResetConfirmView, PersonaDetailView, PersonaPrivacyView, PersonaPublicDetailView, ProfileImageUploadView, RefreshTokenView, RegisterView, LoginView, RequestPasswordResetView, SaveMyLocationView, ToggleEventLikeView, UserProfileView, UtentePublicDetailView
from .views import (
    SendFriendRequestView, RespondFriendRequestView, CancelFriendRequestView,
    UnfriendView, MyFriendsListView, PendingRequestsView, ListaPersoneConFriendshipView
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path("attiva/<uidb64>/<token>/", ActivateAccountView.as_view(), name="attiva-account"),
    path("auth/password-reset/", RequestPasswordResetView.as_view(), name="password-reset"),
    path("auth/password-reset-confirm/<uidb64>/<token>/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path('login/', LoginView.as_view(), name='login'),
    path("logout/", LogoutView.as_view()),
    path("token/refresh/", RefreshTokenView.as_view()),
    path("eventi/", EventiView.as_view(), name="eventi"),
    path('lista-eventi/', ListaEventiView.as_view(), name='lista_eventi'),
    path('utenti/', ListaPersoneView.as_view(), name='lista_utenti'),
    path('locali/', ListaLocaliView.as_view(), name='lista_locali'),
    path('me/persona/', PersonaDetailView.as_view(), name='me-persona'),
    path('me/locale/', LocaleDetailView.as_view(), name='me-locale'),
    path('me/profile-image', ProfileImageUploadView.as_view(), name='me-profile-image'),
    path('me/', UserProfileView.as_view(), name='me'),
    path('utenti/<int:user_id>/', UtentePublicDetailView.as_view(), name='utente-detail'),
    path('eventi/locale/<int:locale_id>/', EventiPerLocaleView.as_view(), name='eventi_per_locale'),
    path("me/privacy/persona", PersonaPrivacyView.as_view(), name="persona-privacy"),
    path("me/privacy/locale",  LocalePrivacyView.as_view(),  name="locale-privacy"),
    path("users/me/location", SaveMyLocationView.as_view(), name="save_my_location"),
    path("eventi/<int:pk>/", EventoDetailView.as_view(), name="evento-detail"),
    path("eventi/<int:event_id>/toggle-like/", ToggleEventLikeView.as_view(), name="eventi-toggle-like"),
    path("friends/requests", SendFriendRequestView.as_view(), name="friends-send"),
    path("friends/requests/<int:fr_id>/respond", RespondFriendRequestView.as_view(), name="friends-respond"),
    path("friends/requests/<int:fr_id>/cancel", CancelFriendRequestView.as_view(), name="friends-cancel"),
    path("friends/<int:other_user_id>", UnfriendView.as_view(), name="friends-unfriend"),
    path("friends", MyFriendsListView.as_view(), name="friends-list"),
    path("friends/requests/pending", PendingRequestsView.as_view(), name="friends-pending"),
    path("persone/friendship", ListaPersoneConFriendshipView.as_view(), name="persone-friendship"),
    path("people/friends-and-suggested/", FriendsAndSuggestedView.as_view(), name="friends-and-suggested"),
]
