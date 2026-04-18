import React, { useState } from 'react'

const ASSETS = ["Elevator", "Low-Pressure Boiler", "Facade (Pre-War)", "Commercial Kitchen", "Street Tree"]

function Poker() {
    const [budget, setBudget] = useState(50000)
    const [dealtCards, setDealtCards] = useState([])
    const [selectedAssets, setSelectedAssets] = useState([])
    const [gameOver, setGameOver] = useState(false)

    const startGame = () => {
        setBudget(50000)
        setDealtCards([])
        setSelectedAssets([])
        setGameOver(false)
    }

    const addAsset = async (asset) => {
        if (selectedAssets.includes(asset)) return
        setSelectedAssets(prev => [...prev, asset])

        try {
            const response = await fetch('http://localhost:8005/api/random_penalty')
            const penalty = await response.json()

            setDealtCards(prev => [...prev, { ...penalty, id: Date.now() }])
            setBudget(prev => {
                const newBudget = prev - penalty.fine
                if (newBudget <= 0) setGameOver(true)
                return newBudget
            })
        } catch (error) {
            console.error("Error fetching random penalty:", error)
        }
    }

    return (
        <div style={{ border: '2px solid black', padding: '2rem', background: 'white' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '2rem' }}>
                <div>
                    <h2 style={{ color: 'var(--color-burgundy)' }}>PENALTY POKER</h2>
                    <p style={{ fontWeight: 600 }}>SURVIVE THE REGULATORY BLUFF. YOUR BUDGET IS YOUR LIFE.</p>
                </div>
                <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '2rem', fontWeight: 800, color: budget > 10000 ? 'var(--color-green)' : 'var(--color-red)' }}>
                        ${budget.toLocaleString()}
                    </div>
                    <div style={{ fontSize: '0.75rem', fontWeight: 800 }}>REMAINING OPERATING BUDGET</div>
                </div>
            </div>

            {!gameOver ? (
                <>
                    <div style={{ marginBottom: '2rem' }}>
                        <h3 style={{ fontSize: '0.875rem', marginBottom: '1rem' }}>ADD ASSETS TO YOUR PORTFOLIO:</h3>
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                            {ASSETS.map(a => (
                                <button
                                    key={a}
                                    className="btn btn-outline"
                                    onClick={() => addAsset(a)}
                                    disabled={selectedAssets.includes(a)}
                                >
                                    + {a}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div>
                        <h3 style={{ fontSize: '0.875rem', marginBottom: '1rem' }}>ACTIVE VIOLATIONS (YOUR HAND):</h3>
                        <div className="poker-deck">
                            {dealtCards.map(c => (
                                <div key={c.id} className="card penalty">
                                    <div>
                                        <div style={{ fontSize: '0.75rem', fontWeight: 800 }}>VIOLATION</div>
                                        <h2 style={{ fontSize: '1.25rem', margin: '0.5rem 0' }}>{c.title}</h2>
                                        <p style={{ fontSize: '0.75rem', color: 'black' }}>{c.desc}</p>
                                    </div>
                                    <div style={{ borderTop: '1px solid currentColor', paddingTop: '1rem' }}>
                                        <div style={{ fontSize: '1.5rem', fontWeight: 800 }}>-${c.fine}</div>
                                        <div style={{ fontSize: '0.6rem', color: 'black' }}>REF: {c.citation}</div>
                                    </div>
                                </div>
                            ))}
                            {selectedAssets.length === 0 && (
                                <div style={{ opacity: 0.3, border: '2px dashed black', padding: '4rem', width: '100%', textAlign: 'center' }}>
                                    SELECT AN ASSET TO BEGIN INSPECTION
                                </div>
                            )}
                        </div>
                    </div>
                </>
            ) : (
                <div style={{ textAlign: 'center', padding: '4rem 0' }}>
                    <h1 style={{ color: 'var(--color-red)' }}>INSOLVENT</h1>
                    <p style={{ fontWeight: 600, marginBottom: '2rem' }}>YOU HAVE BEEN BURIED IN RED TAPE. TOTAL PENALTIES EXCEEDED BUDGET.</p>
                    <button className="btn btn-green" onClick={startGame}>RE-INCORPORATE</button>
                </div>
            )}
        </div>
    )
}

export default Poker
