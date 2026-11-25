const docUrl = './Planificacao_Projeto_Registo_Entradas_Saidas.docx.docx';
const wordContent = document.getElementById('word-content');
const loadButton = document.getElementById('load-word');
const previewDocButton = document.getElementById('preview-doc-button');

const fallbackHtml = `
  <h2>Projeto Tecnológico · Registo de Entradas e Saídas</h2>
  <p><strong>Descrição:</strong> Sistema para registar entradas e saídas da sala de aula com identificação rápida, dados organizados e consulta posterior.</p>
  <h3>Objetivos específicos</h3>
  <ul>
    <li>Identificar cada pessoa de forma rápida.</li>
    <li>Registar data, hora e tipo de evento.</li>
    <li>Guardar a informação numa base de dados organizada.</li>
    <li>Disponibilizar uma interface de consulta com filtros.</li>
    <li>Exportar relatórios em CSV ou PDF.</li>
    <li>Garantir a proteção dos dados pessoais.</li>
  </ul>
  <h3>Calendarização</h3>
  <p>Plano em oito semanas: levantamento, solução, base de dados, desenvolvimento, consulta, testes, documentação e apresentação.</p>
`;

async function renderDocxFromUrl(url) {
  if (!wordContent) return;

  wordContent.innerHTML = '<p>A carregar o conteúdo do documento...</p>';

  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error('Não foi possível carregar o ficheiro Word.');
    }

    const arrayBuffer = await response.arrayBuffer();
    const result = await mammoth.convertToHtml({ arrayBuffer });
    wordContent.innerHTML = result.value || fallbackHtml;
  } catch (error) {
    console.error(error);
    wordContent.innerHTML = fallbackHtml;
  }
}

if (loadButton) {
  loadButton.addEventListener('click', () => renderDocxFromUrl(docUrl));
}

if (previewDocButton) {
  previewDocButton.addEventListener('click', () => {
    document.getElementById('documento').scrollIntoView({ behavior: 'smooth' });
    renderDocxFromUrl(docUrl);
  });
}

if (typeof mammoth !== 'undefined') {
  renderDocxFromUrl(docUrl);
} else {
  wordContent.innerHTML = fallbackHtml;
}
