from fastsdk import FastClient, APISeex
from typing import Union

from media_toolkit import AudioFile, MediaFile


class speechcraft(FastClient):
    """
    Create audio from text, clone voices and use them. Convert voice2voice. Generative text-to-audio Bark model.
    """
    def __init__(self, api_key: str = None):
        super().__init__(service_name_or_id="1fc6c59f-bbd4-43e3-8c3e-4f18466cfa3a", api_key=api_key)
    
    def health(self, **kwargs) -> APISeex:
        """
        Get server health status.
        
        Returns:
            HTTP response with health status
        
        """
        return self.submit_job("/health", **kwargs)
    
    def text2voice(self, text: str, voice: Union[bytes, MediaFile, str] = 'en_speaker_3', semantic_temp: float = 0.7, semantic_top_k: int = 50, semantic_top_p: float = 0.95, coarse_temp: float = 0.7, coarse_top_k: int = 50, coarse_top_p: float = 0.95, fine_temp: float = 0.5, **kwargs) -> APISeex:
        """
        :param text: the text to be converted
        :param voice: the name of the voice to be used. Uses the pretrained voices which are stored in models/speakers folder.
            It is also possible to provide a full path.
        :return: the audio file as bytes
        
        """
        return self.submit_job("/text2voice", text=text, voice=voice, semantic_temp=semantic_temp, semantic_top_k=semantic_top_k, semantic_top_p=semantic_top_p, coarse_temp=coarse_temp, coarse_top_k=coarse_top_k, coarse_top_p=coarse_top_p, fine_temp=fine_temp, **kwargs)
    
    def voice2embedding(self, audio_file: Union[bytes, AudioFile, str], voice_name: str = 'new_speaker', save: bool = False, **kwargs) -> APISeex:
        """
        :param audio_file: the audio file as bytes 5-20s is good length
        :param voice_name: how the new voice / embedding is named
        :param save: if the embedding should be saved in the voice dir for reusage.
            Note: depending on the server settings this might not be allowed
        :return: the voice embedding as bytes
        
        """
        return self.submit_job("/voice2embedding", audio_file=audio_file, voice_name=voice_name, save=save, **kwargs)
    
    def voice2voice(self, audio_file: Union[bytes, AudioFile, str], voice_name: Union[bytes, MediaFile, str] = 'en_speaker_3', temp: float = 0.7, **kwargs) -> APISeex:
        """
        :param audio_file: the audio file as bytes 5-20s is good length
        :param voice_name: the new of the voice to convert to; or the voice embedding. String or MediaFile.
        :param temp: generation temperature (1.0 more diverse, 0.0 more conservative)
        :return: the converted audio file as bytes
        
        """
        return self.submit_job("/voice2voice", audio_file=audio_file, voice_name=voice_name, temp=temp, **kwargs)
    
    # Convenience aliases for the primary endpoint
    run = health
    __call__ = health
