"""Engines de simulação do projeto Condor X.

Este pacote não controla dispositivos e não descreve hardware físico. Ele
opera somente sobre fontes abstratas de empuxo e dados fornecidos pelo usuário.
"""

from .propulsion_lab import PropulsionLabEngine

__all__ = ["PropulsionLabEngine"]
