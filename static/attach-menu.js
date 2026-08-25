/* МЕНЮ ВЛОЖЕНИЯ: СНЯТЬ НА КАМЕРУ ИЛИ ВЗЯТЬ ИЗ ГАЛЕРЕИ.
 *
 * Системный компонент с 2026-08-25. Потребителей два — переписка
 * дневника питания и панель ассистента аптечки; до этого ~18 строк
 * лежали ИНЛАЙНОМ в `templates/nutrition.html` при одном потребителе,
 * и копия для аптечки стала бы ровно тем дублем, против которого
 * заведена задача 126. Та же дорога, что прошли `voice-input.js`
 * и `image-resize.js`.
 *
 * Разметка страничная (два скрытых поля файла и кнопки меню), поведение
 * общее. Обработчик «клик вне меню» вешается ОДИН раз на документ:
 * два таких обработчика гасили бы меню друг друга непредсказуемо.
 */
function toggleAttachMenu(btn) {
  const menu = btn.nextElementSibling;
  const open = menu.style.display === 'flex';
  document.querySelectorAll('.attach-menu').forEach(m => m.style.display = 'none');
  menu.style.display = open ? 'none' : 'flex';
}

function pickAttach(btn, inputId) {
  btn.closest('.attach-menu').style.display = 'none';
  document.getElementById(inputId).click();
}

/* Закрываем открытое меню по нажатию вне его */
document.addEventListener('click', (e) => {
  if (e.target.closest('.attach-wrap')) return;
  document.querySelectorAll('.attach-menu').forEach(m => m.style.display = 'none');
});
