from datetime import timedelta
from rest_framework_simplejwt.exceptions import TokenError
from django.forms import BooleanField, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status,generics, permissions
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth import get_user_model
from api.models import EventLike, Evento, FriendRequest, Locale, Persona, Utente
from api.pagination import FriendsPagination, SuggestedPagination
from api.utils import _get_user_coords_or_params, _parse_bool, _parse_float, annotate_distance_km, annotate_friendship_status, send_activation_email, send_password_reset_email
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from .serializers import LOCALE_PUBLIC_FIELDS, PERSONA_PUBLIC_FIELDS, EventoSerializer, FriendRequestActionSerializer, FriendRequestSerializer, LocalePrivacySerializer, LocaleSerializer, PersonaListSerializer, PersonaListWithFriendshipSerializer, PersonaPrivacySerializer, PersonaSerializer, RegistrazioneSerializer, LoginSerializer, User, UserLocationInSerializer
from .serializers import PersonaDetailSerializer, LocaleDetailSerializer
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, SAFE_METHODS
from django.db.models import Count, Exists, OuterRef, Value, BooleanField,Q,Case, When, Subquery,IntegerField
from django.utils import timezone
from datetime import date
from django.db import models


class RegisterView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = RegistrazioneSerializer(data=request.data)
        if serializer.is_valid():

            user = serializer.save()
            send_activation_email(user, request)

            return Response({
                "messaggio": "Registrazione completata. Controlla la tua email per confermare l’account."
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class ActivateAccountView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, uidb64, token):
        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = get_user_model().objects.get(pk=uid)
        except Exception:
            user = None

        if user and default_token_generator.check_token(user, token):
            user.is_active = True
            user.save()
            # 🔁 Redirect al FE dopo l'attivazione
            return redirect(f"{settings.FRONTEND_BASE_URL}/email-confermata")
        
        return redirect(f"{settings.FRONTEND_BASE_URL}/email-non-valida")
        
class RequestPasswordResetView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({"detail": "Email richiesta"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            send_password_reset_email(user, request, uid, token)  # da implementare
        except User.DoesNotExist:
            pass  # per non rivelare se l'email esiste o no

        return Response({"detail": "Se l'indirizzo è registrato, riceverai un'email per il reset."}, status=status.HTTP_200_OK)
    
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, uidb64, token):
        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "Link non valido"}, status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, token):
            return Response({"detail": "Token scaduto o non valido"}, status=status.HTTP_400_BAD_REQUEST)

        new_password = request.data.get("password")
        if not new_password:
            return Response({"detail": "La nuova password è obbligatoria"}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()

        return Response({"detail": "Password aggiornata con successo"}, status=status.HTTP_200_OK)

class LoginView(APIView):
    permission_classes = [AllowAny]

    def _display_name(self, user):
        try:
            if getattr(user, "tipo", None) == "persona":
                p = Persona.objects.only("nome", "cognome").get(utente=user)
                full = f"{(p.nome or '').strip()} {(p.cognome or '').strip()}".strip()
                return full or (user.email.split("@")[0] if user.email else str(user.id))
            elif getattr(user, "tipo", None) == "locale":
                l = Locale.objects.only("nome_locale").get(utente=user)
                return (l.nome_locale or "").strip() or (user.email.split("@")[0] if user.email else str(user.id))
        except (Persona.DoesNotExist, Locale.DoesNotExist):
            pass
        # fallback generico
        return user.email.split("@")[0] if getattr(user, "email", None) else str(user.id)

    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            detail = e.detail
            if isinstance(detail, dict) and "detail" in detail and detail.get("code") == "not_confirmed":
                return Response(detail, status=status.HTTP_403_FORBIDDEN)
            return Response(detail, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data['user']

        # 🔁 leggo il flag dal body; default False
        resta_connesso = bool(request.data.get("resta_connesso", False))

        # ⏳ crea refresh token e imposta la scadenza ad-hoc
        refresh = RefreshToken.for_user(user)

        # Imposta scadenza personalizzata del refresh
        if resta_connesso:
            refresh.set_exp(lifetime=timedelta(days=30))  # es: 30 giorni
            cookie_max_age = 30 * 24 * 60 * 60
        else:
            refresh.set_exp(lifetime=timedelta(days=1))   # es: 1 giorno
            cookie_max_age = None  # cookie di sessione (si cancella alla chiusura del browser)

        access_token = str(refresh.access_token)

        payload = {
            "access": access_token,
            "user": {
                "id": user.id,
                "tipo": getattr(user, "tipo", None),
                "name": self._display_name(user),
                # opzionale: utile al FE
                "email": getattr(user, "email", None),
            },
        }

        response = JsonResponse(payload)
        response.set_cookie(
            key="refresh_token",
            value=str(refresh),
            httponly=True,
            samesite="None",   # 👈 aggiungi
            secure=True,
            max_age=cookie_max_age,  # None => session cookie
            path="/",
        )
        return response
    
class RefreshTokenView(APIView):
    permission_classes=[AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get("refresh_token")
        if not refresh_token:
            return Response({"detail": "Token mancante"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            refresh = RefreshToken(refresh_token)
            new_access = str(refresh.access_token)
            return Response({"access": new_access})
        except TokenError:
            return Response({"detail": "Token non valido o scaduto"}, status=status.HTTP_401_UNAUTHORIZED)
        
class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        response = Response(status=status.HTTP_205_RESET_CONTENT)
        response.delete_cookie(
            "refresh_token",
            path="/",
            samesite="None",   # 👈 aggiungi
            secure=True        # 👈 aggiungi (coerente con set)
        )
        return response
   


class ListaEventiView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    queryset = Evento.objects.all().order_by('-data_evento')
    serializer_class = EventoSerializer


class ListaPersoneView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    queryset = Persona.objects.select_related('utente').all()
    serializer_class = PersonaListSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

class ListaLocaliView(generics.ListAPIView):
    permission_classes = [AllowAny]
    queryset = Locale.objects.select_related('utente').all()
    serializer_class = LocaleSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({"request": self.request})
        return context

    def get_queryset(self):
        qs = Locale.objects.select_related('utente').all()

        qp = self.request.query_params
        nome = qp.get("nome")
        citta = qp.get("citta")
        solo_con_eventi = _parse_bool(qp.get("soloConEventi"))
        ordina_per_distanza = _parse_bool(qp.get("ordinaPerDistanza"))
        raggio_km = _parse_float(qp.get("raggioKm"))
        lat_param = _parse_float(qp.get("lat"))
        lng_param = _parse_float(qp.get("lng"))

        data_str = qp.get("data")
        try:
            ref_date = date.fromisoformat(data_str) if data_str else timezone.localdate()
        except ValueError:
            ref_date = timezone.localdate()

        # testo
        if nome:
            qs = qs.filter(nome_locale__icontains=nome)
        if citta:
            qs = qs.filter(indirizzo__icontains=citta)

        # solo locali che hanno almeno un evento
        if solo_con_eventi:
            qs = qs.annotate(
                eventi_oggi=Count("evento", filter=Q(evento__data_evento=ref_date))
            ).filter(eventi_oggi__gt=0)

        # distanza
        user_lat, user_lng = _get_user_coords_or_params(self.request, lat_param, lng_param)
        qs = annotate_distance_km(qs, lat_field="latitudine", lng_field="longitudine",
                                  user_lat=user_lat, user_lng=user_lng)

        # filtro raggio
        if (user_lat is not None and user_lng is not None) and (raggio_km is not None):
            qs = qs.filter(distance_km__lte=raggio_km)

        # ordinamento
        if ordina_per_distanza and user_lat is not None and user_lng is not None:
            qs = qs.order_by("distance_km", "nome_locale")
        else:
            qs = qs.order_by("nome_locale")

        return qs


class EventiPerLocaleView(generics.ListAPIView):
    serializer_class = EventoSerializer
    def get_queryset(self):
        locale_id = self.kwargs['locale_id']
        return Evento.objects.filter(locale_id=locale_id).order_by('-data_evento')
    
def clean_patch_data(data: dict, *, is_persona: bool) -> dict:
    """
    - Rimuove chiavi con valore None (ignora non toccati)
    - Converte '' -> None per i campi NON stringa (es. date)
    - Per Persona: vieta nome/cognome vuoti o solo spazi se presenti
    """
    cleaned: dict = {}
    for k, v in data.items():
        # ignora null - campo non toccato
        if v is None:
            continue

        # normalizza date ('' -> None)
        if k in ('data_nascita',):
            if isinstance(v, str) and v.strip() == '':
                cleaned[k] = None
            else:
                cleaned[k] = v
            continue
        if k == 'delete_image':   # 👈 lascia passare il flag
            cleaned[k] = v
            continue

        # per altri campi, lasciamo anche '' per clear (string fields)
        cleaned[k] = v

    # vincolo persona: nome/cognome se presenti devono avere >=1 char
    if is_persona:
        for field in ('nome', 'cognome'):
            if field in cleaned:
                val = cleaned[field]
                if not isinstance(val, str) or len(val.strip()) < 1:
                    return {"__error__": (field, "Deve contenere almeno 1 carattere")}
    return cleaned


class PersonaDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = PersonaDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return Persona.objects.get(utente=self.request.user)

    def patch(self, request, *args, **kwargs):
        partial = True
        raw = request.data.dict() if hasattr(request.data, 'dict') else dict(request.data)
        cleaned = clean_patch_data(raw, is_persona=True)

        instance = self.get_object()

        # 👇 Gestione delete_image: cancella file + setta None
        delete_flag = cleaned.pop("delete_image", None)
        if delete_flag in (True, "true", "True", "1", 1, "on"):
            if instance.profile_image:
                instance.profile_image.delete(save=False)
            instance.profile_image = None
            instance.save(update_fields=["profile_image"])

        serializer = self.get_serializer(instance, data=cleaned, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class PersonaPublicDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PersonaListSerializer
    lookup_url_kwarg = "user_id"

    def get_object(self):
        user_id = self.kwargs[self.lookup_url_kwarg]
        return get_object_or_404(
            Persona.objects.select_related("utente"),
            utente__id=user_id
        )



class LocaleDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = LocaleDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return Locale.objects.get(utente=self.request.user)

    def patch(self, request, *args, **kwargs):
        partial = True
        raw = request.data.dict() if hasattr(request.data, 'dict') else dict(request.data)
        cleaned = clean_patch_data(raw, is_persona=False)

        instance = self.get_object()

        delete_flag = cleaned.pop("delete_image", None)
        if delete_flag in (True, "true", "True", "1", 1, "on"):
            if instance.profile_image:
                instance.profile_image.delete(save=False)
            instance.profile_image = None
            instance.save(update_fields=["profile_image"])

        serializer = self.get_serializer(instance, data=cleaned, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data, status=status.HTTP_200_OK)



class ProfileImageUploadView(APIView):
    """
    POST /api/me/profile-image  (multipart/form-data con 'file')
    Aggiorna Persona.profile_image o Locale.profile_image (in base a user.tipo)
    Ritorna: { "url": "<MEDIA_URL...>" }
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        user = request.user
        f = request.FILES.get("file")
        if not f:
            return Response({"detail": "file mancante"}, status=status.HTTP_400_BAD_REQUEST)

        if user.tipo == "persona":
            try:
                persona = Persona.objects.get(utente=user)
            except Persona.DoesNotExist:
                return Response({"detail": "Profilo persona non trovato"}, status=404)
            persona.profile_image = f
            persona.save(update_fields=["profile_image"])
            url = persona.profile_image.url if persona.profile_image else None
        elif user.tipo == "locale":
            try:
                locale = Locale.objects.get(utente=user)
            except Locale.DoesNotExist:
                return Response({"detail": "Profilo locale non trovato"}, status=404)
            locale.profile_image = f
            locale.save(update_fields=["profile_image"])
            url = locale.profile_image.url if locale.profile_image else None
        else:
            return Response({"detail": "Tipo utente non supportato"}, status=400)

        # URL assoluta per comodità FE
        abs_url = request.build_absolute_uri(url) if url else None
        return Response({"url": abs_url}, status=status.HTTP_200_OK)

class UserProfileView(APIView):
    permission_classes = [IsAuthenticated] 

    def get(self, request):
        user = request.user

        if user.tipo == "persona":
            try:
                persona = Persona.objects.select_related('utente').get(utente=user)
                serializer = PersonaDetailSerializer(persona, context={"request": request})  # 👈
                return Response({
                    "tipo": "persona",
                    "profilo": serializer.data
                })
            except Persona.DoesNotExist:
                return Response({"detail": "Profilo persona non trovato"}, status=404)

        elif user.tipo == "locale":
            try:
                locale = Locale.objects.select_related('utente').get(utente=user)
                serializer = LocaleDetailSerializer(locale, context={"request": request})  # 👈
                return Response({
                    "tipo": "locale",
                    "profilo": serializer.data
                })
            except Locale.DoesNotExist:
                return Response({"detail": "Profilo locale non trovato"}, status=404)

        return Response({"detail": "Tipo utente non supportato"}, status=400)
    
class UtentePublicDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id: int):
        # Prendo solo quello che serve
        user = get_object_or_404(Utente.objects.only("id", "tipo"), id=user_id)

        if user.tipo == "persona":
            persona = get_object_or_404(
                Persona.objects.select_related("utente"),
                utente__id=user.id
            )
            serializer = PersonaListSerializer(persona, context={"request": request})
            return Response({"tipo": "persona", "profilo": serializer.data})

        if user.tipo == "locale":
            locale = get_object_or_404(
                Locale.objects.select_related("utente"),
                utente__id=user.id
            )
            serializer = LocaleSerializer(locale, context={"request": request})
            return Response({"tipo": "locale", "profilo": serializer.data})

        return Response({"detail": "Tipo utente non supportato"}, status=400)

class SaveMyLocationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        # ⛔️ Utenti 'locale': ignoriamo la richiesta (posizione fissa)
        if getattr(user, "tipo", None) == "locale":
            # Puoi anche restituire 204 No Content se preferisci
            return Response({"ok": True, "ignored": True, "reason": "fixed_location"}, status=200)

        # ✅ Solo 'persona' viene salvata
        ser = UserLocationInSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        try:
            persona = Persona.objects.get(utente=user)
        except Persona.DoesNotExist:
            return Response({"detail": "Profilo persona non trovato"}, status=404)

        persona.last_lat = data["lat"]
        persona.last_lng = data["lng"]
        persona.last_accuracy = data["accuracy"]
        persona.last_loc_ts = data.get("ts")
        persona.save(update_fields=["last_lat", "last_lng", "last_accuracy", "last_loc_ts"])

        return Response({"ok": True}, status=200)
    
    
class PersonaPrivacyView(APIView):
    """
    GET  /api/me/privacy/persona   -> legge i campi nascosti + opzioni disponibili
    PATCH /api/me/privacy/persona  -> aggiorna i campi nascosti (owner persona)
    Body: { "hidden_fields": ["data_nascita","telefono", ...] }
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if getattr(request.user, "tipo", None) != "persona":
            return Response({"detail": "Non sei un profilo persona"}, status=400)

        persona = get_object_or_404(Persona, utente=request.user)
        return Response({
            "hidden_fields": persona.hidden_fields or [],
            "available_fields": [f for f in PERSONA_PUBLIC_FIELDS if f not in ("nome", "cognome")],
            "always_public": ["nome", "cognome"],
        })

    def patch(self, request):
        if getattr(request.user, "tipo", None) != "persona":
            return Response({"detail": "Non sei un profilo persona"}, status=400)

        persona = get_object_or_404(Persona, utente=request.user)
        ser = PersonaPrivacySerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        hidden = ser.validated_data["hidden_fields"]
        # Hard-guard: nome/cognome restano sempre pubblici
        hidden = [f for f in hidden if f not in ("nome", "cognome")]

        persona.hidden_fields = hidden
        persona.save(update_fields=["hidden_fields"])
        return Response({"hidden_fields": persona.hidden_fields}, status=200)


class LocalePrivacyView(APIView):
    """
    GET  /api/me/privacy/locale    -> legge i campi nascosti + opzioni disponibili
    PATCH /api/me/privacy/locale   -> aggiorna i campi nascosti (owner locale)
    Body: { "hidden_fields": ["telefono_contatto", ...] }
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if getattr(request.user, "tipo", None) != "locale":
            return Response({"detail": "Non sei un profilo locale"}, status=400)

        locale = get_object_or_404(Locale, utente=request.user)
        return Response({
            "hidden_fields": locale.hidden_fields or [],
            "available_fields": list(LOCALE_PUBLIC_FIELDS),
        })

    def patch(self, request):
        if getattr(request.user, "tipo", None) != "locale":
            return Response({"detail": "Non sei un profilo locale"}, status=400)

        locale = get_object_or_404(Locale, utente=request.user)
        ser = LocalePrivacySerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        locale.hidden_fields = ser.validated_data["hidden_fields"]
        locale.save(update_fields=["hidden_fields"])
        return Response({"hidden_fields": locale.hidden_fields}, status=200)

def annotate_likes(qs, user):
    """
    Aggiunge:
      - like_count: numero like
      - is_liked: se l'utente corrente ha messo like
    """
    qs = qs.annotate(
        like_count=Count("likes", distinct=True),
    )
    if user and getattr(user, "is_authenticated", False):
        qs = qs.annotate(
            is_liked=Exists(
                EventLike.objects.filter(event=OuterRef("pk"), user=user)
            )
        )
    else:
        qs = qs.annotate(is_liked=Value(False, output_field=BooleanField()))
    return qs
    
class EventiView(generics.ListCreateAPIView):
    queryset = Evento.objects.select_related("locale", "locale__utente").all().order_by("-data_evento", "-orario_evento")
    serializer_class = EventoSerializer
    parser_classes = (MultiPartParser, FormParser)

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        base = super().get_queryset()
        qs = annotate_likes(base, self.request.user)

        qp = self.request.query_params

        titolo = qp.get("titolo")          # ricerca solo nel titolo
        luogo = qp.get("luogo")
        data = qp.get("data")              # "YYYY-MM-DD"
        orario = qp.get("orario")          # "HH:MM" o "HH:MM:SS"
        prezzo_max = qp.get("prezzoMax")
        free_only = str(qp.get("freeOnly", "")).lower() in {"true", "1", "yes", "y", "on"}
        locale_nome = qp.get("localeNome")
        ordina_per_data = str(qp.get("ordinaPerData", "")).lower() in {"true", "1", "yes", "y", "on"}
        ordina_per_orario = str(qp.get("ordinaPerOrario", "")).lower() in {"true", "1", "yes", "y", "on"}

        if titolo:
            qs = qs.filter(titolo__icontains=titolo)

        if luogo:
            qs = qs.filter(luogo__icontains=luogo)

        if data:
            # match esatto sul giorno
            qs = qs.filter(data_evento=data)

        if orario:
            # Django può castare stringa "HH:MM" in TimeField
            qs = qs.filter(orario_evento=orario)

        if free_only:
            qs = qs.filter(Q(prezzo__isnull=True) | Q(prezzo=0))
        else:
            if prezzo_max not in (None, "", "null"):
                try:
                    max_val = float(prezzo_max)
                    # includi anche eventi senza prezzo
                    qs = qs.filter(Q(prezzo__isnull=True) | Q(prezzo__lte=max_val))
                except ValueError:
                    pass

        if locale_nome:
            qs = qs.filter(locale__nome_locale__icontains=locale_nome)

        # ORDINAMENTO:
        # - default: come queryset (data e orario DESC)
        # - se richiesto il sort per data/orario, passo ad ASC per avere "più vicine → più lontane"
        if ordina_per_data or ordina_per_orario:
            order_fields = []
            if ordina_per_data:
                order_fields.append("data_evento")     # ASC
            if ordina_per_orario:
                order_fields.append("orario_evento")   # ASC
            if order_fields:
                qs = qs.order_by(*order_fields)

        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

    def perform_create(self, serializer):
        utente = self.request.user
        if getattr(utente, "tipo", None) != "locale":
            raise PermissionDenied("Solo i profili 'locale' possono creare eventi.")
        locale = Locale.objects.get(utente=utente)
        serializer.save(locale=locale)

class IsEventoOwnerOrReadOnly(BasePermission):
    """
    GET/HEAD/OPTIONS -> sempre consentito
    PATCH/PUT/DELETE -> solo owner (utente locale che possiede l'evento)
    """
    def has_permission(self, request, view):
        # Lettura pubblica
        if request.method in SAFE_METHODS:
            return True
        # Scrittura: serve autenticazione
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj: Evento):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        return (
            getattr(user, "tipo", None) == "locale"
            and obj.locale.utente_id == user.id
        )

class EventoDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Evento.objects.select_related("locale", "locale__utente").all()
    serializer_class = EventoSerializer
    permission_classes = [IsEventoOwnerOrReadOnly]
    parser_classes = (MultiPartParser, FormParser)

    def get_queryset(self):
        base = super().get_queryset()
        return annotate_likes(base, self.request.user)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

    def perform_update(self, serializer):
        instance: Evento = self.get_object()
        delete_flag = self.request.data.get("delete_locandina")
        delete_truthy = str(delete_flag).lower() in {"true", "1", "on", "yes"}
        has_new_file = bool(self.request.FILES.get("locandina"))

        obj = serializer.save()

        if delete_truthy and not has_new_file:
            if instance.locandina:
                instance.locandina.delete(save=False)
            instance.locandina = None
            instance.save(update_fields=["locandina"])

        return obj

class ToggleEventLikeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, event_id: int):
        event = get_object_or_404(Evento, pk=event_id)
        like, created = EventLike.objects.get_or_create(event=event, user=request.user)
        if created:
            return Response({"status": "liked", "event_id": event.id}, status=status.HTTP_201_CREATED)
        like.delete()
        return Response({"status": "unliked", "event_id": event.id}, status=status.HTTP_200_OK)
    
class SendFriendRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        to_user_id = request.data.get("to_user_id")
        if not to_user_id:
            return Response({"detail": "to_user_id richiesto"}, status=400)

        if int(to_user_id) == request.user.id:
            return Response({"detail": "Non puoi richiederla a te stesso"}, status=400)

        try:
            to_user = Utente.objects.get(id=to_user_id)
        except Utente.DoesNotExist:
            return Response({"detail": "Utente non trovato"}, status=404)

        fr = FriendRequest(from_user=request.user, to_user=to_user)
        fr.save()
        return Response(FriendRequestSerializer(fr).data, status=201)


class RespondFriendRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, fr_id: int):
        try:
            fr = FriendRequest.objects.get(id=fr_id)
        except FriendRequest.DoesNotExist:
            return Response({"detail": "Richiesta non trovata"}, status=404)

        if fr.to_user_id != request.user.id:
            return Response({"detail": "Non autorizzato"}, status=403)

        ser = FriendRequestActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        action = ser.validated_data["action"]

        if fr.status != "pending":
            return Response({"detail": "Richiesta già gestita"}, status=400)

        fr.status = "accepted" if action == "accept" else "declined"
        fr.responded_at = timezone.now()
        fr.save(update_fields=["status", "responded_at"])

        return Response(FriendRequestSerializer(fr).data, status=200)


class CancelFriendRequestView(APIView):
    """Il mittente può cancellare la sua pending."""
    permission_classes = [IsAuthenticated]

    def post(self, request, fr_id: int):
        try:
            fr = FriendRequest.objects.get(id=fr_id, from_user=request.user, status="pending")
        except FriendRequest.DoesNotExist:
            return Response({"detail": "Richiesta non trovata o non cancellabile"}, status=404)
        fr.status = "canceled"
        fr.responded_at = timezone.now()
        fr.save(update_fields=["status", "responded_at"])
        return Response(FriendRequestSerializer(fr).data, status=200)


class UnfriendView(APIView):
    """Rimuove l'amicizia accettata (da entrambe le direzioni)."""
    permission_classes = [IsAuthenticated]

    def delete(self, request, other_user_id: int):
        qs = FriendRequest.objects.filter(
            Q(from_user=request.user, to_user_id=other_user_id) |
            Q(from_user_id=other_user_id, to_user=request.user),
            status="accepted",
        )
        if not qs.exists():
            return Response({"detail": "Non siete amici"}, status=404)
        qs.delete()
        return Response(status=204)


class MyFriendsListView(APIView):
    """Solo amici ACCETTATI, restituiti come persone (profili 'persona')."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # ids amici
        accepted = FriendRequest.objects.filter(
            Q(from_user=request.user) | Q(to_user=request.user),
            status="accepted",
        )
        friend_ids = set()
        for fr in accepted.only("from_user_id", "to_user_id"):
            friend_ids.add(fr.from_user_id if fr.to_user_id == request.user.id else fr.to_user_id)

        persone = Persona.objects.select_related("utente").filter(utente__id__in=friend_ids, utente__tipo="persona")
        ser = PersonaListSerializer(persone, many=True, context={"request": request})
        return Response(ser.data, status=200)


class PendingRequestsView(APIView):
    """incoming/outgoing pendenti."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        incoming = FriendRequest.objects.filter(to_user=request.user, status="pending").select_related("from_user")
        outgoing = FriendRequest.objects.filter(from_user=request.user, status="pending").select_related("to_user")
        return Response({
            "incoming": FriendRequestSerializer(incoming, many=True).data,
            "outgoing": FriendRequestSerializer(outgoing, many=True).data,
        }, status=200)
    
# api/views.py
class ListaPersoneConFriendshipView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PersonaListWithFriendshipSerializer

    def get_queryset(self):
        qs = Persona.objects.select_related("utente").filter(utente__tipo="persona")
        qs = annotate_friendship_status(qs, self.request.user)
        # ordina: friend -> incoming -> outgoing -> none -> self (ultimo)
        ordering = Case(
            When(friendship_status="friend", then=Value(0)),
            When(friendship_status="incoming", then=Value(1)),
            When(friendship_status="outgoing", then=Value(2)),
            When(friendship_status="none", then=Value(3)),
            default=Value(9),
            output_field=models.IntegerField(),
        )
        return qs.order_by(ordering, "utente__id")

class FriendsAndSuggestedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        base_qs = (
            Persona.objects
            .select_related("utente")
            .filter(utente__tipo="persona")
            .exclude(utente=request.user)
        )
        qs = annotate_friendship_status(base_qs, request.user)

        # Subquery per prendere l'id della FR "incoming" (loro -> me), pending
        incoming_fr_id = Subquery(
            FriendRequest.objects.filter(
                from_user_id=OuterRef("utente__id"),
                to_user_id=request.user.id,
                status="pending",
            ).values("id")[:1]
        )

        # Subquery per "outgoing" (io -> loro), pending (se vuoi usarla)
        outgoing_fr_id = Subquery(
            FriendRequest.objects.filter(
                from_user_id=request.user.id,
                to_user_id=OuterRef("utente__id"),
                status="pending",
            ).values("id")[:1]
        )

        # Annotiamo un unico campo 'friend_request_id' scegliendo in base allo status
        qs = qs.annotate(
            friend_request_id=Case(
                When(friendship_status="incoming", then=incoming_fr_id),
                When(friendship_status="outgoing", then=outgoing_fr_id),
                default=Value(None, output_field=IntegerField()),
                output_field=IntegerField(),
            )
        )

        # --- Friends (accepted) ---
        friends_qs = qs.filter(friendship_status="friend").order_by("utente__id")

        friends_paginator = FriendsPagination()
        friends_page = friends_paginator.paginate_queryset(friends_qs, request, view=self)
        friends_ser = PersonaListWithFriendshipSerializer(
            friends_page, many=True, context={"request": request}
        ).data

        friends_data = {
            "count": friends_paginator.page.paginator.count,
            "page": friends_paginator.page.number,
            "page_size": friends_paginator.get_page_size(request),
            "next": friends_paginator.get_next_link(),
            "previous": friends_paginator.get_previous_link(),
            "results": friends_ser,
        }

        # --- Incoming / Outgoing (non paginati) ---
        incoming_qs = qs.filter(friendship_status="incoming").order_by("utente__id")
        outgoing_qs = qs.filter(friendship_status="outgoing").order_by("utente__id")

        ser_ctx = {"request": request}
        incoming_data = PersonaListWithFriendshipSerializer(incoming_qs, many=True, context=ser_ctx).data
        outgoing_data = PersonaListWithFriendshipSerializer(outgoing_qs, many=True, context=ser_ctx).data

        # --- Suggested (none) ---
        suggested_qs = qs.filter(friendship_status="none").order_by("utente__id")
        suggested_paginator = SuggestedPagination()
        suggested_page = suggested_paginator.paginate_queryset(suggested_qs, request, view=self)
        suggested_ser = PersonaListWithFriendshipSerializer(suggested_page, many=True, context=ser_ctx).data

        suggested_data = {
            "count": suggested_paginator.page.paginator.count,
            "page": suggested_paginator.page.number,
            "page_size": suggested_paginator.get_page_size(request),
            "next": suggested_paginator.get_next_link(),
            "previous": suggested_paginator.get_previous_link(),
            "results": suggested_ser,
        }

        return Response({
            "friends": friends_data,
            "incoming": incoming_data,
            "outgoing": outgoing_data,
            "suggested": suggested_data,
        })