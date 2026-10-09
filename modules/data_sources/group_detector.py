"""
Модуль для визначення активної групи на основі аварій DTEK.
"""

import logging
import re

logger = logging.getLogger(__name__)


def extract_group_number(group_name):
    """
    Витягує номер групи з назви.
    
    Args:
        group_name: Назва групи (наприклад "GPV6.2")
    
    Returns:
        str: Номер групи ("6.2") або None
    """
    # Шукаємо патерн: GPV + число (може бути з крапкою)
    match = re.search(r'GPV(\d+(?:\.\d+)?)', group_name)
    if match:
        return match.group(1)
    
    # Якщо патерн не знайдено, але є число в кінці
    match = re.search(r'(\d+(?:\.\d+)?)$', group_name)
    if match:
        return match.group(1)
    
    logger.warning(f"⚠️ Не вдалося витягти номер з групи '{group_name}'")
    return None


def find_most_affected_group(alarms_groups):
    """
    Знаходить групу з найбільшою кількістю будинків, що мають аварії.
    
    Args:
        alarms_groups: Словник з групами аварій
    
    Returns:
        str: Номер групи (наприклад "6.2") або None якщо аварій немає
    """
    if not alarms_groups:
        logger.info("📊 Аварій немає - використовуємо групу з .env")
        return None
    
    # Підраховуємо будинки по групах
    group_counts = {}
    
    for alarm_info in alarms_groups.values():
        houses = alarm_info.get('houses', [])
        
        for house in houses:
            # Отримуємо інформацію про групу
            if isinstance(house, dict):
                group_name = house.get('group', '')
                house_number = house.get('number', '')
            else:
                # Старий формат - немає інформації про групу
                continue
            
            if group_name:
                # Витягуємо номер групи з назви (наприклад "GPV6.2" -> "6.2")
                group_number = extract_group_number(group_name)
                if group_number:
                    if group_number not in group_counts:
                        group_counts[group_number] = set()
                    # Додаємо номер будинку до множини (щоб не враховувати дублікати)
                    group_counts[group_number].add(house_number)
    
    if not group_counts:
        logger.info("📊 Не знайдено інформації про групи в аваріях - використовуємо групу з .env")
        return None
    
    # Знаходимо групу з найбільшою кількістю будинків
    most_affected_group = max(group_counts.items(), key=lambda x: len(x[1]))
    group_number = most_affected_group[0]
    houses_count = len(most_affected_group[1])
    
    logger.info(f"🎯 Найбільш уражена група: {group_number} ({houses_count} будинків)")
    logger.info(f"📊 Статистика груп: {', '.join(f'{g}: {len(h)} буд.' for g, h in sorted(group_counts.items()))}")
    
    return group_number
