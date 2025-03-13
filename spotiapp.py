import os
import random
import time
from flask import Flask, request, render_template, redirect, url_for, session as flask_session
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import Column, Integer, String, ForeignKey, create_engine, Float

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    nombre = Column(String)
    edad = Column(Integer)
    pais = Column(String)
    correo = Column(String, unique=True)  # Unique email field
    genero_favorito = Column(String)

class UserTrackRating(Base):
    __tablename__ = 'user_track_ratings'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    track_id = Column(String(255))
    rating = Column(Float)

    
engine = create_engine('sqlite:///users.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db_session = Session()

def save_user(nombre, edad, pais, correo, genero_favorito):
    # Check if the user already exists
    existing_user = db_session.query(User).filter_by(correo=correo).first()
    if existing_user:
        print("User already exists in the database.")
        return

    # If the user does not exist, save the new user
    new_user = User(nombre=nombre, edad=edad, pais=pais, correo=correo, genero_favorito=genero_favorito)
    db_session.add(new_user)
    db_session.commit()
    print("User saved successfully.")

def save_track_rating(user_id, track_id, rating):
    try:
        existing_rating = db_session.query(UserTrackRating).filter_by(user_id=user_id, track_id=track_id).first()
        if existing_rating:
            existing_rating.rating = rating
        else:
            new_rating = UserTrackRating(user_id=user_id, track_id=track_id, rating=rating)
            db_session.add(new_rating)
        db_session.commit()
    except Exception as e:
        print(f"Error saving track rating: {e}")
        db_session.rollback()

def get_user_track_ratings():
    try:
        return db_session.query(UserTrackRating).all()
    except Exception as e:
        print(f"Error getting user track ratings: {e}")
        return []
    
def get_collaborative_recommendations(user_id, tracks):
    try:
        ratings = get_user_track_ratings()
        user_ids = []
        track_ids = []
        rating_matrix = {}
        for rating in ratings:
            user_id_ = rating.user_id
            track_id_ = rating.track_id
            rating_ = rating.rating
            if user_id_ not in rating_matrix:
                rating_matrix[user_id_] = {}
            rating_matrix[user_id_][track_id_] = rating_
            if user_id_ not in user_ids:
                user_ids.append(user_id_)
            if track_id_ not in track_ids:
                track_ids.append(track_id_)
        user_index_map = {user_id: index for index, user_id in enumerate(user_ids)}
        track_index_map = {track_id: index for index, track_id in enumerate(track_ids)}
        matrix = np.zeros((len(user_ids), len(track_ids)))
        for user_id_, track_ratings in rating_matrix.items():
            user_index = user_index_map[user_id_]
            for track_id_, rating_ in track_ratings.items():
                track_index = track_index_map[track_id_]
                matrix[user_index, track_index] = rating_
        user_similarity = cosine_similarity(matrix)
        current_user_index = user_index_map.get(user_id)
        if current_user_index is None:
            return []
        similarities = user_similarity[current_user_index]
        similar_users_indices = similarities.argsort()[::-1][1:11]
        recommended_track_ids = set()
        for user_index in similar_users_indices:
            similar_user_id = user_ids[user_index]
            similar_user_ratings = rating_matrix.get(similar_user_id, {})
            user_ratings = rating_matrix.get(user_id, {})
            for track_id, rating in similar_user_ratings.items():
                if track_id not in user_ratings and rating > 3:
                    recommended_track_ids.add(track_id)
        recommended_tracks = [track for track in tracks if track['id'] in recommended_track_ids]
        return recommended_tracks
    except Exception as e:
        print(f"Error getting collaborative recommendations: {e}")
        return []    

app = Flask("BackyardFeelings")
app.secret_key = 'supersecretkey'  # Needed for session to work

# Credenciales de Spotify (REEMPLAZA ESTO CON TUS CREDENCIALES REALES)
CLIENT_ID = '0da023b7c4c840f39df4528da8ffb09f'
CLIENT_SECRET = '5b315b07bdbd43a0816a5c27ecfeac1f'

# Autenticación con Spotify
spotify = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET))

# Géneros y estados de ánimo disponibles
GENRES = ['pop', 'hip hop', 'rock', 'electronic', 'indie', 'jazz', 'country', 'classical', 'r&b', 'latin']
MOODS = ['happy', 'sad', 'chill', 'energetic', 'romantic']

# Configure Spotify OAuth
sp_oauth = SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri='http://127.0.0.1:5000/callback',  # Ensure this matches
    scope='user-library-read'
)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    return 'Authentication successful!'

# Function to read from CSV file
def read_csv_file(file_path):
    if os.path.exists(file_path) and os.stat(file_path).st_size > 0:
        return pd.read_csv(file_path)
    else:
        return pd.DataFrame(columns=['nombre', 'edad', 'pais', 'correo', 'genero_favorito'])  # Return empty DataFrame with columns if file doesn't exist or is empty

# Function to write to CSV file
def write_csv_file(file_path, data_frame):
    data_frame.to_csv(file_path, index=False)

# Load user ratings data from CSV file
csv_file_path = r"C:\Users\jemis\Downloads\api spoti\ratings.csv"
data = read_csv_file(csv_file_path)

@app.route('/register', methods=['POST'])
def register():
    nombre = request.form.get('nombre')
    edad = request.form.get('edad')
    pais = request.form.get('pais')
    correo = request.form.get('correo')
    genero_favorito = request.form.get('genero_favorito')

    save_user(nombre, edad, pais, correo, genero_favorito)

    mensaje_usuario = "Datos guardados exitosamente"
    return render_template('index.html', mensaje_usuario=mensaje_usuario, genres=GENRES, moods=MOODS, tracks=None, auth_url=sp_oauth.get_authorize_url())

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html', genres=GENRES, moods=MOODS, tracks=None, auth_url=sp_oauth.get_authorize_url(), mensaje_usuario=None)

@app.route('/show_playlist')
def show_playlist():
    selected_tracks = flask_session.get('selected_tracks', [])
    return render_template('playlist.html', tracks=selected_tracks)

@app.route('/playlist', methods=['POST'])
def playlist():
    artist = request.form.get('artist', '').strip()
    genre = request.form.get('genre', '').strip()
    mood = request.form.get('mood', '').strip()

    # Build query parts only if a value is provided.
    query_parts = []
    if artist:
        query_parts.append(f'artist:"{artist}"')
    if genre:
        query_parts.append(f'genre:"{genre}"')
    # Note: Spotify doesn't officially support a "mood" search qualifier.
    if mood:
        query_parts.append(f'mood:"{mood}"')  

    # Join the parts with a space.
    query = " ".join(query_parts)
    print("Search Query:", query)  # Debug: Verify the query string.

    results = spotify.search(q=query, type='track', limit=50)
    tracks = results['tracks']['items']

    if not tracks:
        # If the query returns no results, try a fallback without the mood qualifier.
        query_parts = []
        if artist:
            query_parts.append(f'artist:"{artist}"')
        if genre:
            query_parts.append(f'genre:"{genre}"')
        query = " ".join(query_parts)
        results = spotify.search(q=query, type='track', limit=50)
        tracks = results['tracks']['items']

    # Process tracks with clustering...
    data_dict = {'popularity': [track['popularity'] for track in tracks]}
    data_df = pd.DataFrame(data_dict)
    data_df['track'] = tracks

    data_df = data_df.sort_values(by='popularity', ascending=True)
    scaler = StandardScaler()
    scaled_popularity = scaler.fit_transform(data_df[['popularity']])
    n_clusters = min(20, len(tracks))
    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
    data_df['cluster'] = kmeans.fit_predict(scaled_popularity)

    seed = int(time.time())
    random.seed(seed)
    selected_tracks = []
    for cluster in data_df['cluster'].unique():
        cluster_tracks = data_df[data_df['cluster'] == cluster]
        if not cluster_tracks.empty:
            selected_track_index = random.choice(cluster_tracks.index)
            selected_track_id = data_df.loc[selected_track_index, 'track']['id']
            for track in tracks:
                if track['id'] == selected_track_id:
                    selected_tracks.append(track)
                    break

    # Render the playlist immediately.
    return render_template('playlist.html', tracks=selected_tracks)

if __name__ == '__main__':
    app.run(debug=True)
