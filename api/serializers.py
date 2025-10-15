from datetime import date
from rest_framework import serializers
from django.contrib.auth import authenticate

from api.serializer_utils import AbsoluteURLMixin
from .models import FriendRequest, Utente, Persona, Locale

class RegistrazioneSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    tipo = serializers.ChoiceField(choices=[('persona', 'Persona'), ('locale', 'Locale')])

    # persona
    nome = serializers.CharField(required=False)
    cognome = serializers.CharField(required=False)
    data_nascita = serializers.DateField(required=False)
    telefono = serializers.CharField(required=False, allow_blank=True)

    # locale
    nome_locale = serializers.CharField(required=False)
    indirizzo = serializers.CharField(required=False)
    partita_iva = serializers.CharField(required=False)
    telefono_contatto = serializers.CharField(required=False)
    latitudine = serializers.FloatField(required=False)
    longitudine = serializers.FloatField(required=False)

    def create(self, validated_data):
        tipo = validated_data['tipo']
        password = validated_data.pop('password')
        email = validated_data['email']

        try:
            existing_user = Utente.objects.get(email=email)
            if existing_user.is_active:
                raise serializers.ValidationError({"email": "Email già in uso"})
            else:
                raise serializers.ValidationError({"email": "Utente già registrato in attesa di conferma email"})
        except Utente.DoesNotExist:
            pass  # ok, utente non esiste: possiamo crearlo
            utente = Utente.objects.create_user(email=email, password=password, tipo=tipo)

        if tipo == 'persona':
            Persona.objects.create(
                utente=utente,
                nome=validated_data.get('nome', ''),
                cognome=validated_data.get('cognome', ''),
                data_nascita=validated_data.get('data_nascita'),
                telefono=validated_data.get('telefono')
            )
        elif tipo == 'locale':
            Locale.objects.create(
                utente=utente,
                nome_locale=validated_data.get('nome_locale', ''),
                indirizzo=validated_data.get('indirizzo', ''),
                partita_iva=validated_data.get('partita_iva'),
                telefono_contatto=validated_data.get('telefono_contatto'),
                latitudine=validated_data.get('latitudine'),
                longitudine=validated_data.get('longitudine')
            )

        return utente

    
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password

User = get_user_model()

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, data):
        email = data.get("email")
        password = data.get("password")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"detail":"Utente non registrato","code":"not_exist"})

        # ❌ Account non confermato
        if not user.is_active:
            raise serializers.ValidationError(
                {"detail": "Account non confermato!", "code": "not_confirmed"}
            )

        # ✅ Controllo password
        if not user.check_password(password):
            raise serializers.ValidationError({"detail": "Credenziali non valide", "code": "not_confirmed"})

        return {"user": user}


from .models import Evento

class EventoSerializer(serializers.ModelSerializer):
    locandina = serializers.ImageField(required=False, allow_null=True, use_url=True)
    locandina_url = serializers.SerializerMethodField()
    copertina_img = serializers.ImageField(required=False, allow_null=True, use_url=True)
    copertina_url = serializers.SerializerMethodField()
    orario_evento = serializers.TimeField(required=True, format="%H:%M", input_formats=["%H:%M", "%H:%M:%S"])
    luogo = serializers.CharField(required=False, allow_blank=True)
    prezzo = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, allow_null=True)
    posti_disponibili = serializers.IntegerField(required=False, allow_null=True)
    locale_id = serializers.IntegerField(source="locale.id", read_only=True)
    locale_nome = serializers.CharField(source="locale.nome_locale", read_only=True) 
    utente_id = serializers.IntegerField(source="locale.utente_id", read_only=True)
    telefono = serializers.CharField(source="locale.telefono_contatto", read_only=True)
    altre_informazioni = serializers.CharField(required=False, allow_blank=True)
    programma = serializers.CharField(required=False, allow_blank=True)
    informazioni_utili = serializers.CharField(required=False, allow_blank=True)

    like_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.BooleanField(read_only=True)

    class Meta:
        model = Evento
        fields = [
            "id", "titolo", "descrizione",
            "data_evento", "orario_evento",
            "luogo", "prezzo", "posti_disponibili",
            "locale_id", "locale_nome","utente_id","telefono",
            "locandina", "locandina_url","copertina_img","copertina_url","creato_il","like_count", "is_liked", "programma", "altre_informazioni", "informazioni_utili"
        ]
        read_only_fields = ["creato_il"]

    def get_locandina_url(self, obj):
        req = self.context.get("request")
        if obj.locandina and hasattr(obj.locandina, "url"):
            url = obj.locandina.url
            return req.build_absolute_uri(url) if req else url
        return None
    
    def get_copertina_url(self, obj):
        req = self.context.get("request")
        if obj.copertina_img and hasattr(obj.copertina_img, "url"):
            url = obj.copertina_img.url
            return req.build_absolute_uri(url) if req else url
        return None

    # Facoltativo: converte "" -> None per i numerici quando arriva multipart/form-data
    def validate(self, attrs):
        for f in ("prezzo", "posti_disponibili"):
            if attrs.get(f) == "":
                attrs[f] = None
        return attrs

class UtenteBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Utente
        fields = ['id', 'email', 'tipo']

# === Whitelist dei campi pubblicabili ===
PERSONA_PUBLIC_FIELDS = (
    "nome", "cognome","email",
    "sesso", "data_nascita","eta",
    "telefono", "situazione_sentimentale",
    "profile_image",
)

LOCALE_PUBLIC_FIELDS = (
    "nome_locale",
    "indirizzo",
    "telefono_contatto",
    "profile_image",
    "longitudine",
    "latitudine",
    "email",  
)


class PersonaPrivacySerializer(serializers.Serializer):
    hidden_fields = serializers.ListField(
        child=serializers.ChoiceField(
            choices=[f for f in PERSONA_PUBLIC_FIELDS if f not in ("nome", "cognome")]
        ),
        allow_empty=True
    )

class LocalePrivacySerializer(serializers.Serializer):
    hidden_fields = serializers.ListField(
        child=serializers.ChoiceField(choices=list(LOCALE_PUBLIC_FIELDS)),
        allow_empty=True
    )

class LocaleSerializer(AbsoluteURLMixin, serializers.ModelSerializer):
    utente = UtenteBaseSerializer(read_only=True)
    profile_image = serializers.SerializerMethodField()
    email = serializers.EmailField(source="utente.email", read_only=True)

    class Meta:
        model = Locale
        fields = (
            "utente",
            "nome_locale",
            "indirizzo",
            "telefono_contatto",
            "profile_image",
            "longitudine",
            "latitudine",
            "email"
        )

    def get_profile_image(self, obj: Locale):
        if not obj.profile_image:
            return None
        return self.build_abs_url(obj.profile_image.url)

    def to_representation(self, instance: Locale):
        data = super().to_representation(instance)
        request = self.context.get("request")
        viewer_id = getattr(getattr(request, "user", None), "id", None)
        owner_id = getattr(getattr(instance, "utente", None), "id", None)

        if viewer_id and owner_id and int(viewer_id) == int(owner_id):
            return data

        filtered = {}
        for k, v in data.items():
            if k in ("utente",):
                filtered[k] = v
            else:
                filtered[k] = v if instance.is_public(k) else None
        return filtered

class PersonaSerializer(serializers.ModelSerializer):
    utente = UtenteBaseSerializer()
    email = serializers.EmailField(source="utente.email", read_only=True)

    class Meta:
        model = Persona
        fields = ['utente', 'nome', 'cognome', 'telefono','data_nascita','email']

class PersonaListSerializer(AbsoluteURLMixin, serializers.ModelSerializer):
    utente = UtenteBaseSerializer(read_only=True)
    profile_image = serializers.SerializerMethodField()
    eta = serializers.SerializerMethodField()

    class Meta:
        model = Persona
        fields = (
            "utente",
            "nome", "cognome",
            "sesso", "data_nascita","eta",
            "telefono", "situazione_sentimentale",
            "profile_image",
        )

    def get_profile_image(self, obj: Persona):
        if not obj.profile_image:
            return None
        # NON applico la privacy qui: la gestisco in to_representation per coerenza su tutti i campi.
        return self.build_abs_url(obj.profile_image.url)
    
    def get_eta(self, obj):
        if obj.data_nascita:
            today = date.today()
            return (
                today.year - obj.data_nascita.year
                - ((today.month, today.day) < (obj.data_nascita.month, obj.data_nascita.day))
            )
        return None

    def to_representation(self, instance: Persona):
        data = super().to_representation(instance)
        request = self.context.get("request")
        viewer_id = getattr(getattr(request, "user", None), "id", None)
        owner_id = getattr(getattr(instance, "utente", None), "id", None)

        # Owner vede sempre tutto
        if viewer_id and owner_id and int(viewer_id) == int(owner_id):
            return data

        # Applica privacy per i non-owner
        filtered = {}
        for k, v in data.items():
            if k in ("utente", "nome", "cognome"):
                filtered[k] = v
            else:
                # profile_image compresa: se non è pubblica → None
                filtered[k] = v if instance.is_public(k) else None
        return filtered


class PersonaDetailSerializer(serializers.ModelSerializer):
    utente = UtenteBaseSerializer(read_only=True)
    eta = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()
    email = serializers.EmailField(source="utente.email", read_only=True)


    class Meta:
        model = Persona
        fields = [
            'utente', 'nome', 'cognome', 'telefono','email',
            'data_nascita', 'sesso', 'situazione_sentimentale',
            'profile_image', 'eta', 'last_lat', 'last_lng'
        ]
        read_only_fields = ['utente', 'eta']

    def get_profile_image(self, obj):
        if not obj.profile_image:
            return None
        request = self.context.get("request")
        url = obj.profile_image.url
        return request.build_absolute_uri(url) if request else url

    def get_eta(self, obj):
        if obj.data_nascita:
            today = date.today()
            return (
                today.year - obj.data_nascita.year
                - ((today.month, today.day) < (obj.data_nascita.month, obj.data_nascita.day))
            )
        return None

class LocaleDetailSerializer(serializers.ModelSerializer):
    utente = UtenteBaseSerializer(read_only=True)
    profile_image = serializers.SerializerMethodField() 
    email = serializers.EmailField(source="utente.email", read_only=True)

    class Meta:
        model = Locale
        fields = [
            'utente', 'nome_locale', 'indirizzo',
            'partita_iva', 'telefono_contatto',
            'latitudine', 'longitudine', 'profile_image','email'
        ]
        read_only_fields = ['utente']

    def get_profile_image(self, obj):
        if not obj.profile_image:
            return None
        request = self.context.get("request")
        url = obj.profile_image.url
        return request.build_absolute_uri(url) if request else url
    

class UserLocationInSerializer(serializers.Serializer):
    lat = serializers.DecimalField(max_digits=11, decimal_places=7, min_value=-90, max_value=90)
    lng = serializers.DecimalField(max_digits=11, decimal_places=7, min_value=-180, max_value=180)
    accuracy = serializers.FloatField(min_value=0)
    ts = serializers.DateTimeField()

class FriendRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = FriendRequest
        fields = ("id", "from_user", "to_user", "status", "created_at", "responded_at")
        read_only_fields = ("status", "created_at", "responded_at")

class FriendRequestActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["accept", "decline"])

# estensione del PersonaListSerializer
class PersonaListWithFriendshipSerializer(PersonaListSerializer):
    friendship_status = serializers.CharField(read_only=True)
    friend_request_id = serializers.IntegerField(read_only=True, required=False, allow_null=True)

    class Meta(PersonaListSerializer.Meta):
        fields = PersonaListSerializer.Meta.fields + ("friendship_status", "friend_request_id")
