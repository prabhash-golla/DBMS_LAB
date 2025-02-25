import { useState,useEffect } from 'react'

function App() {
  const [ai,setAi] = useState([]);

  useEffect(()=>{
    async function fetchData(){
    console.log(import.meta.env.VITE_API_URL)
    try {
      const response = await fetch(`${import.meta.env.VITE_API_URL}posts`,{
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      if(!response.ok){
        throw new Error('Network Sending Response not Found');
      }
      const result = await response.json();
      console.log(result);
      setAi(result);
    } catch(e){
      console.log("Error Fetching the data:",e);
    }
    }
    
    fetchData();
  },[])

  return (
    <>
      <h1>Data from API:</h1>
      <ul>
        {ai.map((item, index) => (
          <li key={index}>{JSON.stringify(item)}</li>
        ))}
      </ul>
    </>
  )
}

export default App
