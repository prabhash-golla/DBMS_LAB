import { useState,useEffect } from 'react'

function App() {
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
    } catch(e){
      console.log("Error Fetching the data:",e);
    }
    }
    
    fetchData();
  },[])

  return (
    <>
    
    </>
  )
}

export default App
