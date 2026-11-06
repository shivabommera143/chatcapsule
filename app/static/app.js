let latest;

const $ = id => document.getElementById(id);
const download = (name, type, body) => {
    const url = URL.createObjectURL(new Blob([body], { type }));
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    link.click();
    URL.revokeObjectURL(url);
};

$('generate').onclick = async () => {
    const status = $('status');
    const button = $('generate');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 35_000);

    status.textContent = 'Extracting conversation...';
    status.dataset.state = 'loading';
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.textContent = 'Generating capsule...';
    $('result').classList.add('hidden');

    try {
        const response = await fetch('/api/capsule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: $('url').value }),
            signal: controller.signal,
        });
        const data = await response.json().catch(() => null);
        if (!response.ok) {
            throw new Error(data?.detail || `The server returned an error (${response.status}).`);
        }
        if (!data) {
            throw new Error('The server returned an unreadable response. Please try again.');
        }

        status.textContent = 'Building context capsule...';
        latest = data;
        $('title').textContent = data.conversation.title || 'Untitled conversation';
        $('capsule').value = data.markdown;
        $('original').href = data.conversation.source_url;
        $('stats').innerHTML = Object.entries(data.statistics)
            .map(([key, value]) => `<span>${key.replaceAll('_', ' ')}: ${value}</span>`)
            .join('');
        $('result').classList.remove('hidden');
        status.textContent = '';
        delete status.dataset.state;
    } catch (error) {
        status.textContent = error.name === 'AbortError'
            ? 'The request took too long. Please try again.'
            : error.message || 'Unable to generate a capsule. Please try again.';
        status.dataset.state = 'error';
    } finally {
        clearTimeout(timeout);
        button.disabled = false;
        button.removeAttribute('aria-busy');
        button.textContent = 'Generate capsule';
    }
};

$('copy').onclick = async () => {
    try {
        await navigator.clipboard.writeText($('capsule').value);
        $('copy').textContent = 'Copied';
        setTimeout(() => $('copy').textContent = 'Copy capsule', 1600);
    } catch {
        $('copy').textContent = 'Copy unavailable';
        setTimeout(() => $('copy').textContent = 'Copy capsule', 2000);
    }
};
$('md').onclick = () => download('chatcapsule.md', 'text/markdown', $('capsule').value);
$('json').onclick = () => download('chatcapsule.json', 'application/json', JSON.stringify(latest?.capsule, null, 2));
