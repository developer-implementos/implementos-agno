from thefuzz import fuzz


def detectar_objeto_cercano(texto, array, keys, threshold=60, limit=1):
    """
    Busca el objeto más cercano en un array basado en ciertas keys usando fuzzy matching.

    Args:
        texto (str): Texto a buscar
        array (list): Lista de objetos donde buscar
        keys (list): Lista de keys a considerar para la búsqueda
        threshold (int): Umbral de coincidencia (0-100, valor más alto = más estricto)
        limit (int): Número máximo de resultados a devolver

    Returns:
        dict or None: El objeto más cercano encontrado o None si no se encuentra coincidencia
    """
    resultados = []

    for obj in array:
        mejor_puntuacion = 0
        mejor_key = ""
        mejor_valor = ""

        for key in keys:
            if key in obj:
                valor = str(obj[key])

                # Usar ratio para una comparación general
                puntuacion = fuzz.ratio(texto.lower(), valor.lower())

                # Para valores cortos, también probar partial_ratio
                if len(texto) <= 5 or len(valor) <= 5:
                    puntuacion_parcial = fuzz.partial_ratio(texto.lower(), valor.lower())
                    puntuacion = max(puntuacion, puntuacion_parcial)

                if puntuacion > mejor_puntuacion:
                    mejor_puntuacion = puntuacion
                    mejor_key = key
                    mejor_valor = valor

        if mejor_puntuacion >= threshold:
            resultados.append({
                **obj,
                'puntuacion': mejor_puntuacion,
                'key_coincidente': mejor_key,
                'valor_coincidente': mejor_valor
            })

    resultados.sort(key=lambda x: x['puntuacion'], reverse=True)
    resultados = resultados[:limit]

    if resultados:
        return resultados[0] if limit == 1 else resultados
    else:
        return None
