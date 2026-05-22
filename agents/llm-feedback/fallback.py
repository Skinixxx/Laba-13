import logging

logger = logging.getLogger("fallback")


def generate_feedback(
    user_name: str,
    skill_level: str,
    interests: list[str],
    course_name: str,
    assignment_type: str,
    score: int,
    max_score: int,
    passed: bool,
    trend: str,
    avg_score: float,
    **kwargs,
) -> str:
    passed_str = "ПРОЙДЕНО" if passed else "НЕ ПРОЙДЕНО"
    pct = score / max_score * 100 if max_score > 0 else 0

    lines = [
        f"📋 Отзыв для {user_name}",
        f"Курс: {course_name} | Задание: {assignment_type}",
        f"Результат: {score}/{max_score} ({pct:.0f}%) — {passed_str}",
        f"Успеваемость: {trend} | Средний балл: {avg_score:.1f}",
        "",
    ]

    if passed:
        lines.append("✅ Задание выполнено успешно!")
        if pct >= 90:
            lines.append("Отличная работа! Продолжайте в том же духе.")
        elif pct >= 80:
            lines.append("Хороший результат. Есть куда расти.")
        else:
            lines.append("Задание сдано, но стоит уделить внимание ошибкам.")
    else:
        lines.append("❌ Задание не зачтено.")
        lines.append("Рекомендуем повторить материал и попробовать снова.")

    if assignment_type == "test":
        wrong = kwargs.get("wrong_questions", "")
        if wrong:
            lines.append(f"Обратите внимание на вопросы: {wrong}")
        lines.append("Совет: повторите теорию по темам, в которых были ошибки.")
    elif assignment_type == "essay":
        word_count = kwargs.get("word_count", 0)
        lines.append(f"Объём эссе: {word_count} слов.")
        if word_count < 50:
            lines.append("Рекомендуем расширить эссе, раскрывая каждую тему подробнее.")
        keywords = kwargs.get("keywords", "")
        if keywords:
            lines.append(f"Старайтесь раскрыть ключевые понятия: {keywords}")
    elif assignment_type == "code":
        passed_tests = kwargs.get("passed_tests", 0)
        total_tests = kwargs.get("total_tests", 0)
        lines.append(f"Пройдено тестов: {passed_tests}/{total_tests}.")
        lines.append("Проверьте краевые случаи и обработку ошибок в коде.")

    if trend == "declining":
        lines.append("⚠️ Ваши результаты снижаются. Рекомендуем записаться на консультацию.")
    elif trend == "improving":
        lines.append("📈 Виден прогресс! Так держать!")

    if interests:
        lines.append(f"💡 Попробуйте применить знания на практике в области {', '.join(interests)}.")

    lines.append("")
    lines.append("---")
    lines.append("С уважением, система автоматической обратной связи E-Learning")

    return "\n".join(lines)
