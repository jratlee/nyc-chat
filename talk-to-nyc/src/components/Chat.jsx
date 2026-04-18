import React, { useState, useRef, useEffect } from 'react'

const MOCK_BOT_RESPONSES = [
    {
        keywords: ['bee', 'queens', 'honey'],
        response: "According to the NYC Health Code (part of Rules Title 24), you can keep honey bees (Apis mellifera) in New York City, including Queens. However, you must register your hives with the Department of Health and Mental Hygiene (DOHMH) and follow specific hive maintenance rules to prevent public nuisance. (Ref: NYC Rules Title 24, §161.25)"
    },
    {
        keywords: ['dog', 'curb', 'poop', 'fine'],
        response: "NYC Administrative Code §16-121 requires dog owners to remove any feces left by their dog on any public or private property. Failure to do so (the 'Pooper Scooper Law') can result in a fine of $250. This is enforced by both the Department of Sanitation and NYC Parks. (Ref: Admin Code §16-121)"
    },
    {
        keywords: ['sidewalk', 'shed', 'scaffold'],
        response: "Sidewalk sheds are required per Building Code §3307 when a building is undergoing facade work (FISP) or is deemed unsafe. They must be inspected daily by a competent person. As of 2024, the City is transitioning to 'Get Sheds Down' initiatives to replace scaffolding with safety netting where appropriate. (Ref: Admin Code §28-302.2)"
    }
]

function Chat({ sources, search }) {
    const [messages, setMessages] = useState([
        { type: 'bot', text: 'Talk to NYC. What can I help you find today?' }
    ])
    const [input, setInput] = useState('')
    const [isTyping, setIsTyping] = useState(false)
    const messagesEndRef = useRef(null)
    const [sessionId] = useState(crypto.randomUUID())

    const [typingMessage, setTypingMessage] = useState('Analyzing NYC Codes...')

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
    }

    useEffect(() => {
        scrollToBottom()
    }, [messages])

    useEffect(() => {
        let interval
        if (isTyping) {
            const messages = [
                'Consulting Neo4j legal graph...',
                'Traversing Charter hierarchy...',
                'Mapping Administrative Code exceptions...',
                'Synthesizing LLM-grounded response...'
            ]
            let counter = 0
            interval = setInterval(() => {
                setTypingMessage(messages[counter % messages.length])
                counter++
            }, 3000)
        }
        return () => clearInterval(interval)
    }, [isTyping])

    const handleSend = async () => {
        if (!input.trim()) return

        const userMsg = { type: 'user', text: input }
        setMessages(prev => [...prev, userMsg])
        setInput('')
        setIsTyping(true)

        const controller = new AbortController()
        const timeoutId = setTimeout(() => controller.abort(), 180000)

        try {
            const response = await fetch('http://localhost:8005/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    question: input,
                    session_id: sessionId,
                    use_search: search
                }),
                signal: controller.signal
            })

            clearTimeout(timeoutId)
            if (!response.ok) throw new Error('Network response was not ok')

            const reader = response.body.getReader()
            const decoder = new TextDecoder()
            let accumulatedText = ''
            let botMessageCreated = false

            let buffer = ''
            while (true) {
                const { done, value } = await reader.read()
                if (done) break

                buffer += decoder.decode(value, { stream: true })
                const lines = buffer.split('\n\n')
                buffer = lines.pop() // Keep incomplete line in buffer

                for (const line of lines) {
                    if (line.trim().startsWith('data: ')) {
                        const data = line.trim().slice(6)
                        if (!data) continue

                        // Check if it's JSON (metadata) or a text token
                        if (data.startsWith('{') && data.endsWith('}')) {
                            try {
                                const metadata = JSON.parse(data)
                                if (metadata.citations) {
                                    let citationText = `\n\nVerified Citations: ${metadata.citations.map(c => c.n?.id || c.m?.id).filter(id => id).slice(0, 3).join(', ')}`
                                    setMessages(prev => {
                                        const last = prev[prev.length - 1]
                                        if (last && last.type === 'bot') {
                                            return [...prev.slice(0, -1), { ...last, text: last.text + citationText, debug: metadata.debug }]
                                        }
                                        return prev
                                    })
                                }
                            } catch (e) {
                                accumulatedText += data
                            }
                        } else {
                            accumulatedText += data
                            setMessages(prev => {
                                if (!botMessageCreated) {
                                    botMessageCreated = true
                                    setIsTyping(false)
                                    return [...prev, { type: 'bot', text: accumulatedText }]
                                }
                                const last = prev[prev.length - 1]
                                return [...prev.slice(0, -1), { ...last, text: accumulatedText }]
                            })
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Error:', error)
            const errorMsg = error.name === 'AbortError'
                ? "The NYC Legal Graph is deep, and our local LLM is working hard on this complex query."
                : "Error: Could not reach the NYC Regulatory Intelligence Server."
            setMessages(prev => [...prev, { type: 'bot', text: errorMsg }])
        } finally {
            setIsTyping(false)
        }
    }

    return (
        <div className="chat-container">
            <div className="chat-messages">
                {messages.map((m, i) => (
                    <div key={i} className={`message ${m.type}`}>
                        <div style={{ fontSize: '0.65rem', fontWeight: 800, marginBottom: '0.5rem', opacity: 0.5 }}>
                            {m.type === 'user' ? 'YOU' : 'CITY OF NEW YORK'}
                        </div>
                        <div style={{ whiteSpace: 'pre-wrap' }}>{m.text}</div>
                    </div>
                ))}
                {isTyping && <div className="message bot" style={{ opacity: 0.5, fontWeight: 700 }}>{typingMessage}</div>}
                <div ref={messagesEndRef} />
            </div>
            <div className="chat-input-area">
                <input
                    type="text"
                    placeholder="Ask a question about the Charter, Code, or Rules..."
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && handleSend()}
                />
                <button className="btn btn-green" onClick={handleSend}>Query</button>
            </div>
        </div>
    )
}

export default Chat
