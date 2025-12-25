
import urllib.request
import json
import ssl

def test_deepseek():
    url = "https://api.deepseek.com/chat/completions"
    api_key = "sk-ea580c5c98fd456f820507a4acf6d57b"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, are you online?"}
        ],
        "stream": False
    }
    
    print(f"Testing DeepSeek API...")
    print(f"URL: {url}")
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        # Create unverified context to avoid SSL cert issues in some local envs
        context = ssl._create_unverified_context()
        
        with urllib.request.urlopen(req, context=context) as response:
            status = response.getcode()
            body = response.read().decode('utf-8')
            print(f"SUCCESS! Status: {status}")
            print(f"Response: {body[:100]}...")
            return True
            
    except urllib.error.HTTPError as e:
        print(f"HTTP ERROR: {e.code} - {e.reason}")
        print(f"Headers: {e.headers}")
        try:
            error_body = e.read().decode('utf-8')
            print(f"Error Body: {error_body}")
        except:
            pass
        return False
        
    except Exception as e:
        print(f"CONNECTION ERROR: {e}")
        return False

if __name__ == "__main__":
    test_deepseek()
