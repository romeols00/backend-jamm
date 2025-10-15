from django.core.mail import send_mail
from django.urls import reverse
from django.conf import settings
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from typing import Optional
from django.db.models import F, FloatField, Value, ExpressionWrapper, Q, Count
from django.db.models.functions import ACos, Cos, Sin, Radians, Least, Greatest
from django.db.models import Exists, OuterRef, Value, CharField, Q
from .models import FriendRequest
from django.db.models import Case, When, BooleanField

def send_activation_email(user, request):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    activation_url = request.build_absolute_uri(
        reverse("attiva-account", kwargs={"uidb64": uid, "token": token})
    )

    subject = "Conferma la tua registrazione"
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = [user.email]
    text_message = f"Clicca qui per confermare il tuo account: {activation_url}"

    html_message = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1);">
            <h2 style="color: #333;">Benvenuto/a su Jamm!</h2>
            <p style="font-size: 16px; color: #555;">
                Grazie per esserti registrato. Per completare la procedura, clicca sul pulsante qui sotto per confermare il tuo account.
            </p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{activation_url}" style="
                    background-color: #FF4788;
                    color: white;
                    padding: 12px 25px;
                    text-decoration: none;
                    font-size: 16px;
                    border-radius: 5px;
                    display: inline-block;
                ">
                    Conferma Account
                </a>
            </div>
            <p style="font-size: 14px; color: #999;">
                Se non hai richiesto questa email, puoi ignorarla.
            </p>
        </div>
    </body>
    </html>
    """

    send_mail(
        subject=subject,
        message=text_message,  # fallback per client che non leggono HTML
        from_email=from_email,
        recipient_list=to_email,
        html_message=html_message,
        fail_silently=False,
    )

def send_password_reset_email(user, request, uid, token):
    # ✅ URL del frontend, non dell’API
    frontend_url = (f"{settings.FRONTEND_BASE_URL}/reset-password/{uid}/{token}")

    subject = "Reset della tua password"
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = [user.email]
    text_message = f"Clicca qui per reimpostare la tua password: {frontend_url}"

    html_message = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1);">
            <h2 style="color: #333;">Hai richiesto un reset della password</h2>
            <p style="font-size: 16px; color: #555;">
                Abbiamo ricevuto una richiesta per reimpostare la tua password. Clicca sul pulsante qui sotto per scegliere una nuova password.
            </p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{frontend_url}" style="
                    background-color: #FF4788;
                    color: white;
                    padding: 12px 25px;
                    text-decoration: none;
                    font-size: 16px;
                    border-radius: 5px;
                    display: inline-block;
                ">
                    Reimposta Password
                </a>
            </div>
            <p style="font-size: 14px; color: #999;">
                Se non hai richiesto questa email, puoi ignorarla in tutta sicurezza.
            </p>
        </div>
    </body>
    </html>
    """

    send_mail(
        subject=subject,
        message=text_message,
        from_email=from_email,
        recipient_list=to_email,
        html_message=html_message,
        fail_silently=False,
    )




EARTH_RADIUS_KM = 6371.0

def _parse_bool(v: Optional[str]) -> bool:
    if v is None:
        return False
    return str(v).lower() in {"1", "true", "t", "yes", "y", "on"}

def _parse_float(v: Optional[str]) -> Optional[float]:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None

def _get_user_coords_or_params(request, lat_param: Optional[float], lng_param: Optional[float]):
    """
    Se non passate dai query param, prova a prendere last_lat/last_lng della Persona autenticata.
    Ritorna (lat, lng) o (None, None).
    """
    if lat_param is not None and lng_param is not None:
        return lat_param, lng_param

    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False) and getattr(user, "tipo", None) == "persona":
        from api.models import Persona  # evita import ciclico
        try:
            p = Persona.objects.only("last_lat", "last_lng").get(utente=user)
            lat = float(p.last_lat) if p.last_lat is not None else None
            lng = float(p.last_lng) if p.last_lng is not None else None
            return lat, lng
        except Persona.DoesNotExist:
            pass
    return None, None

def annotate_distance_km(queryset, *, lat_field: str, lng_field: str,
                         user_lat: Optional[float], user_lng: Optional[float]):
    """
    Aggiunge .annotate(distance_km=...) usando formula sferica (ACos).
    Se user_lat/lng sono None -> distance_km = NULL.
    Clamp a [-1,1] per evitare errori numerici su ACos.
    """
    if user_lat is None or user_lng is None:
        return queryset.annotate(distance_km=Value(None, output_field=FloatField()))

    inner = (
        Cos(Radians(Value(user_lat))) * Cos(Radians(F(lat_field))) *
        Cos(Radians(F(lng_field)) - Radians(Value(user_lng))) +
        Sin(Radians(Value(user_lat))) * Sin(Radians(F(lat_field)))
    )
    # clamp [-1, 1]
    clamped = Greatest(Value(-1.0), Least(Value(1.0), inner))

    distance_expr = ExpressionWrapper(
        Value(EARTH_RADIUS_KM) * ACos(clamped),
        output_field=FloatField()
    )
    return queryset.annotate(distance_km=distance_expr)

def annotate_friendship_status(qs, me):
    """
    Ritorna qs (di Persona) annotato con 'friendship_status' rispetto a 'me'.
    Valori: 'self' | 'friend' | 'incoming' | 'outgoing' | 'none'
    """
    if not me or not getattr(me, "is_authenticated", False):
        return qs.annotate(friendship_status=Value("none", output_field=CharField()))

    # Persona -> utente collegato
    # Attenzione: Persona ha FK utente (persona.utente)
    outgoing_pending = FriendRequest.objects.filter(from_user=me, to_user=OuterRef("utente_id"), status="pending")
    incoming_pending = FriendRequest.objects.filter(from_user=OuterRef("utente_id"), to_user=me, status="pending")
    accepted_any = FriendRequest.objects.filter(
        Q(from_user=me, to_user=OuterRef("utente_id")) | Q(from_user=OuterRef("utente_id"), to_user=me),
        status="accepted",
    )

    qs = qs.annotate(
        is_self=Value(False, output_field=BooleanField())
    ).annotate(
        outgoing_exists=Exists(outgoing_pending),
        incoming_exists=Exists(incoming_pending),
        accepted_exists=Exists(accepted_any),
    ).annotate(
        friendship_status=Case(
            When(utente_id=me.id, then=Value("self")),
            When(accepted_exists=True, then=Value("friend")),
            When(incoming_exists=True, then=Value("incoming")),
            When(outgoing_exists=True, then=Value("outgoing")),
            default=Value("none"),
            output_field=CharField()
        )
    )
    return qs

# api/views.py (o utils.py)
from django.db.models import Exists, OuterRef, Value, CharField, Q
from .models import FriendRequest

def annotate_friendship_status(qs, me):
    """
    Ritorna qs (di Persona) annotato con 'friendship_status' rispetto a 'me'.
    Valori: 'self' | 'friend' | 'incoming' | 'outgoing' | 'none'
    """
    if not me or not getattr(me, "is_authenticated", False):
        return qs.annotate(friendship_status=Value("none", output_field=CharField()))

    # Persona -> utente collegato
    # Attenzione: Persona ha FK utente (persona.utente)
    outgoing_pending = FriendRequest.objects.filter(from_user=me, to_user=OuterRef("utente_id"), status="pending")
    incoming_pending = FriendRequest.objects.filter(from_user=OuterRef("utente_id"), to_user=me, status="pending")
    accepted_any = FriendRequest.objects.filter(
        Q(from_user=me, to_user=OuterRef("utente_id")) | Q(from_user=OuterRef("utente_id"), to_user=me),
        status="accepted",
    )

    qs = qs.annotate(
        is_self=Value(False, output_field=BooleanField())
    ).annotate(
        outgoing_exists=Exists(outgoing_pending),
        incoming_exists=Exists(incoming_pending),
        accepted_exists=Exists(accepted_any),
    ).annotate(
        friendship_status=Case(
            When(utente_id=me.id, then=Value("self")),
            When(accepted_exists=True, then=Value("friend")),
            When(incoming_exists=True, then=Value("incoming")),
            When(outgoing_exists=True, then=Value("outgoing")),
            default=Value("none"),
            output_field=CharField()
        )
    )
    return qs
