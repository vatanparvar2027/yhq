import os
import logging
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, ID3NoHeaderError

logger = logging.getLogger(__name__)

def set_mp3_tags(file_path: str, title: str, artist: str, cover_path: str = None):
    """
    MP3 fayliga nom, ijrochi va muqova rasmini (cover) biriktirish
    """
    try:
        try:
            audio = MP3(file_path, ID3=ID3)
        except ID3NoHeaderError:
            audio = MP3(file_path)
            audio.add_tags()

        if audio.tags is None:
            audio.add_tags()

        # Nom va ijrochini yozish
        if title:
            audio.tags.add(TIT2(encoding=3, text=title))
        if artist:
            audio.tags.add(TPE1(encoding=3, text=artist))
            audio.tags.add(TALB(encoding=3, text="CHIROQCHIMUZ Music"))

        # Muqova rasmini (cover art) biriktirish
        if cover_path and os.path.exists(cover_path):
            with open(cover_path, "rb") as alb_art:
                audio.tags.add(
                    APIC(
                        encoding=3,
                        mime="image/jpeg",
                        type=3, # Front cover
                        desc="Cover",
                        data=alb_art.read()
                    )
                )

        audio.save()
        logger.info(f"ID3 teglari muvaffaqiyatli saqlandi: {title} - {artist}")
        return True
    except Exception as e:
        logger.warning(f"ID3 teglari o'rnatishda xatolik ({file_path}): {e}")
        return False
